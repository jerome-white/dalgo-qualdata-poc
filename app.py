import os
import json
import logging
import itertools as it
from string import Template
from pathlib import Path
from dataclasses import dataclass

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
class Display:
    def __call__(self, remarks, *args):
        raise NotImplementedError()

class RemarkDisplay(Display):
    _headers = [
        'ID',
        'Remark',
    ]

    def __call__(self, remarks, *args):
        n = len(remarks) + 1
        return {
            'headers': self._headers,
            'data': list(zip(range(1, n), remarks)),
        }

class ChatDisplay(Display):
    _model = 'gpt-3.5-turbo'
    _prompt_root = Path('prompts')
    _prompts = (
        'system',
        'user',
    )

    def __init__(self, **kwargs):
        self.client = OpenAI(api_key=kwargs.get('api_key'))
        self.model = kwargs.get('model', self._model)
        (system, user) = (
            self._prompt_root.joinpath(x).read_text() for x in self._prompts
        )
        self.system_prompt = system
        self.user_prompt = Template(user)

    def __call__(self, remarks, *args):
        (analysis, points) = args
        if not analysis:
            raise ValueError('No summary type selected')

        rmk = '\n'.join(it.starmap('Remark {}: {}'.format, enumerate(remarks)))
        if not rmk:
            raise ValueError('No remarks to consider!')

        user_prompt = self.user_prompt.substitute(
            remarks=rmk,
            analysis=analysis.lower(),
            points=points,
        )
        logging.debug(user_prompt)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=1e-6,
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
            )
        except BadRequestError as err:
            raise InterruptedError(f'{err.type}: {err.code}')

        (message, ) = response.choices
        return message.message.content

#
#
#
class DatabaseManager:
    _table = 'prod.classroom_surveys_normalized'
    _remote = 'postgresql://{user}:{password}@{host}?dbname={dbname}'

    def __init__(self, **kwargs):
        self.con = self._remote.format(**kwargs)

    def query(self, sql):
        logging.debug(' '.join(sql.strip().split()))
        yield from (pd
                    .read_sql_query(sql, con=self.con)
                    .itertuples(index=False))

#
#
#
class Widget:
    def __init__(self, db, name):
        self.db = db
        self.name = name

    def __repr__(self):
        return self.name

    def __str__(self):
        return repr(self).capitalize()

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

class StandardSelectionWidget(DropdownWidget):
    def __init__(self, db, name, column=None, multiselect=True):
        super().__init__(db, name, multiselect)
        self.column = column or self.name

    def options(self):
        sql = f'''
        SELECT DISTINCT {self.column}
        FROM prod.classroom_surveys_normalized
        WHERE {self.column} IS NOT NULL
        ORDER BY {self.column}
        '''

        yield from (getattr(x, self.column) for x in self.db.query(sql))

    def refine(self, values):
        return '{} IN ({})'.format(
            self.column,
            ','.join(map("'{}'".format, values)),
        )

class FormWidget(StandardSelectionWidget):
    def __init__(self, db):
        super().__init__(db, 'activity', 'forms_verbose_consolidated')

class ProgramWidget(StandardSelectionWidget):
    def __init__(self, db):
        super().__init__(db, 'program')

class SummaryWidget(DropdownWidget):
    _stypes = (
        'best practices',
        'areas of improvement',
    )

    def __init__(self, db):
        super().__init__(db, 'type of summary', False)

    def options(self):
        yield from (x.capitalize() for x in self._stypes)

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
        ('sql', ProgramWidget),
        ('sql', DateWidget),
        ('llm', SummaryWidget),
        ('llm', PointsWidget),
    )

    def __init__(self, db, chat, remark):
        self.db = db
        self.chat = chat
        self.remark = remark
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

        remarks = [ x.remark for x in self.db.query(sql) ]
        widgets = list(self['llm'])
        n = len(widgets)
        (summary, points) = (x.refine(y) for (x, y) in zip(widgets, args[-n:]))

        try:
            output = (
                self.chat(remarks, summary, points),
                self.remark(remarks),
            )
        except (ValueError, InterruptedError) as err:
            output = (
                str(err),
                None,
            )

        return output

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

#
#
#
qs_config = Path(os.getenv('QS_CONFIG'))
config = json.loads(qs_config.read_text())

orchestrator = Orchestrator(
    db=DatabaseManager(**config['dalgo']),
    chat=ChatDisplay(**config['open_ai']),
    remark=RemarkDisplay(),
)

inputs = [ x.build() for x in orchestrator ]
demo = gr.Interface(
    fn=orchestrator,
    inputs=inputs,
    outputs=[
        gr.Textbox(
            label='LLM summary',
            show_copy_button=True,
            elem_classes='response',
        ),
        gr.Dataframe(
            label='Remarks on which the summary is based',
            render=False,
            wrap=True,
        ),
    ],
    allow_flagging='never',
    css=Path('style.css'),
)

if __name__ == "__main__":
    kwargs = config.get('gradio') or {}
    demo.queue().launch(**kwargs)
