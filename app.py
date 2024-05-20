import os
import logging
import itertools as it
from string import Template
from pathlib import Path
from dataclasses import dataclass
from configparser import ConfigParser

import pandas as pd
import gradio as gr
from openai import OpenAI, BadRequestError

#
#
#
logging.basicConfig(
    format='[ %(asctime)s %(levelname)s %(filename)s ] %(message)s',
    datefmt='%H:%M:%S',
    level=os.environ.get('PYTHONLOGLEVEL', 'WARNING').upper(),
)

#
#
#
class ChatManager:
    _prompt_root = Path('prompts')
    _prompts = (
        'system',
        'user',
    )

    def __init__(self, config):
        kwargs = dict(config['OPEN_AI'])
        self.client = OpenAI(**kwargs)

        (system, user) = (
            self._prompt_root.joinpath(x).read_text() for x in self._prompts
        )
        self.system_prompt = system
        self.user_prompt = Template(user)

    def __call__(self, remarks, analysis, points):
        rmk = '\n'.join(it.starmap('Remark {}: {}'.format, enumerate(remarks)))
        if not rmk:
            raise ValueError('No remarks to consider!')

        user_prompt = self.user_prompt.substitute(
            remarks=rmk,
            analysis=analysis,
            points=points,
        )
        logging.debug(user_prompt)

        try:
            response = self.client.chat.completions.create(
                model='gpt-3.5-turbo',
                messages=[
                    {
                        'role': 'system',
                        'content': self.system_prompt,
                    },
                    {
                        'role': 'user',
                        'content': user_prompt,
                    },
                ],
                stream=True
            )
        except BadRequestError as err:
            raise InterruptedError(f'{err.type}: {err.code}')

        incoming = []
        for r in response:
            (i, ) = r.choices
            if i.delta.content is not None:
                incoming.append(i.delta.content)
                yield ''.join(incoming)

#
#
#
class DatabaseManager:
    _table = 'prod.classroom_surveys_normalized'
    _remote = 'postgresql://{user}:{password}@{host}?dbname={dbname}'

    def __init__(self, config):
        kwargs = dict(config['DALGO'])
        self.con = self._remote.format(**kwargs)

    def query(self, sql):
        yield from pd.read_sql_query(sql, con=self.con).itertuples(index=False)

#
#
#
class Widget:
    def __init__(self, db, name):
        self.db = db
        self.name = name

    def __str__(self):
        return self.name.capitalize()

    def build(self):
        raise NotImplementedError()

    def refine(self, values):
        raise NotImplementedError()

class DropdownWidget(Widget):
    def __init__(self, db, name, multiselect=True):
        super().__init__(db, name)
        self.multiselect = multiselect

    def build(self):
        choices = list(self.options())
        return gr.Dropdown(
            choices=choices,
            multiselect=self.multiselect,
            label=str(self),
        )

class LocationWidget(DropdownWidget):
    _columns = (
        'country',
        'region',
        # 'sub_region',
    )
    _delimiter = ' / '

    def __init__(self, db):
        super().__init__(db, 'location')

    def options(self):
        sql = '''SELECT DISTINCT {0}
        FROM {2}
        WHERE {1}
        ORDER BY {0}
        '''.format(
            ','.join(self._columns),
            ' AND '.join(map('{} IS NOT NULL'.format, self._columns)),
            self.db._table,
        )

        for i in self.db.query(sql):
            yield f'{i.country}{self._delimiter}{i.region}'

    def refine(self, values):
        elements = []
        for i in values:
            iterable = zip(self._columns, i.split(self._delimiter))
            value = ' AND '.join(it.starmap("{} = '{}'".format, iterable))
            elements.append(value)

        return ' OR '.join(map('({})'.format, elements))

class FormWidget(DropdownWidget):
    _column = 'forms_verbose'
    _focus = set((
        'coaching call',
        'classroom observations',
    ))

    def __init__(self, db):
        super().__init__(db, 'activity', False)

    def qstring(self, value, negate=False):
        yes_no = ' NOT ' if negate else ' '
        return f"LOWER({self._column}){yes_no}LIKE '{value}%%'"

    def options(self):
        for i in it.chain(self._focus, ['other']):
            yield i.capitalize()

    def refine(self, values):
        values = values.lower()

        if values in self._focus:
            sql = self.qstring(values)
        else:
            sql = ' AND '.join(self.qstring(x, True) for x in self._focus)

        return sql

class SummaryWidget(DropdownWidget):
    def __init__(self, db):
        super().__init__(db, 'type of summary', False)

    def options(self):
        yield from (
            'best practices',
            'areas of improvement',
        )

    def refine(self, values):
        return values

class DateWidget(DropdownWidget):
    _column = 'observation_date'

    def __init__(self, db):
        super().__init__(db, 'month')
        self.tmpcol = 'foo'

    def options(self):
        sql = f'''
        SELECT DISTINCT TO_CHAR({self._column}, 'YYYY-MM') AS {self.tmpcol}
        FROM prod.classroom_surveys_normalized
        WHERE {self._column} <= NOW()
        ORDER BY {self.tmpcol} DESC
        '''

        for i in self.db.query(sql):
            yield getattr(i, self.tmpcol)

    def refine(self, values):
        sql = []
        for i in values:
            date = f'{i}-01'
            sql.append(' AND '.join([
                f"{self._column} >= '{date}'",
                f"{self._column} < date '{date}' + interval '1 month'",
            ]))

        return '({})'.format(' OR '.join(map('({})'.format, sql)))

class PointsWidget(Widget):
    _points = 3

    def __init__(self, db):
        super().__init__(db, 'number of points')

    def build(self):
        return gr.Slider(
            value=self._points,
            label=str(self),
            minimum=1,
            maximum=10,
            step=1,
        )

    def refine(self, values):
        return str(values)

#
#
#
@dataclass
class WidgetHolder:
    wtype: str
    widget: Widget

class Orchestrator:
    _widgets = (
        ('sql', LocationWidget),
        ('sql', FormWidget),
        ('sql', DateWidget),
        ('llm', SummaryWidget),
        ('llm', PointsWidget),
    )

    def __init__(self, db, chat):
        self.db = db
        self.chat = chat
        self.widgets = [
            WidgetHolder(x, y(self.db)) for (x, y) in self._widgets
        ]

    def __call__(self, *args):
        logging.info(args)

        where = ' AND '.join(self.refine(*args))
        sql = f'''
        SELECT DISTINCT(TRIM(remarks_qualitative)) AS remark
        FROM {self.db._table}
        WHERE {where}'''
        logging.info(' '.join(sql.strip().split()))

        remarks = (x.remark for x in self.db.query(sql))
        widgets = list(self['llm'])
        n = len(widgets)
        (summary, points) = (x.refine(y) for (x, y) in zip(widgets, args[-n:]))

        yield from self.chat(remarks, summary, points)

    def __iter__(self):
        for i in self.widgets:
            yield i.widget

    def __getitem__(self, item):
        for i in self.widgets:
            if i.wtype == item:
                yield i.widget

    def refine(self, *args):
        for (i, j) in zip(self['sql'], args):
            if j:
                yield i.refine(j)

    @classmethod
    def conduct(cls, *args):
        yield from cls(*args)

# Gradio is not okay with an object that's a yielding callable. This
# function wraps that away so it is happy.
def fn(orchestrator):
    def handler(*args):
        yield from orchestrator(*args)

    return handler

#
#
#
config = ConfigParser()
config.read(os.getenv('QS_CONFIG'))

managers = (x(config) for x in (DatabaseManager, ChatManager))
orchestrator = Orchestrator(*managers)

inputs = [ x.build() for x in orchestrator ]
demo = gr.Interface(
    fn=fn(orchestrator),
    inputs=inputs,
    outputs=[
        gr.Textbox(label='LLM response'),
    ],
    allow_flagging='never',
)

if __name__ == "__main__":
    gr_options = dict(config['GRADIO'])
    kwargs = {
        'share': gr_options.get('share', False),
    }

    auth = tuple(map(gr_options.get, ('username', 'password')))
    if all(auth):
        kwargs['auth'] = auth

    demo.queue().launch(**kwargs)
