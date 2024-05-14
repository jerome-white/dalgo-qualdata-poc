import os
import logging
import itertools as it
from string import Template
from pathlib import Path
from dataclasses import dataclass
from configparser import ConfigParser

import pandas as pd
import gradio as gr
from openai import OpenAI

#
#
#
class ChatInterface:
    _prompt_root = Path('prompts')
    _prompts = (
        'system',
        'user',
    )

    def __init__(self):
        self.client = OpenAI()
        (system, user) = (
            self._prompt_root.joinpath(x).read_text() for x in self._prompts
        )
        self.system_prompt = system
        self.user_prompt = Template(user)

    def __call__(self, remarks, analysis, points):
        rmk = '\n'.join(it.starmap('Remark {}: {}'.format, enumerate(remarks)))
        user_prompt = self.user_prompt.substitute(
            remarks=rmk,
            analysis=analysis,
            points=points,
        )
        logging.critical(user_prompt)
        response = self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        )
        (message, ) = response.choices

        return message.message.content

#
#
#
class DatabaseManager:
    _table = 'prod.classroom_surveys_normalized'

    def __init__(self, host, dbname, user, password):
        self.con = f'postgresql://{user}:{password}@{host}?dbname={dbname}'

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
    _column = 'forms'

    def __init__(self, db):
        super().__init__(db, 'activity')

        self.ftypes_fwd = {
            'cc': 'Coaching call',
            'cro': 'Classroom observation',
        }
        self.ftypes_rev = { y: x for (x, y) in self.ftypes_fwd.items() }

    def options(self):
        sql = '''
        SELECT DISTINCT {1}
        FROM {0}
        WHERE {1} IN ({2})
        '''.format(
            self.db._table,
            self._column,
            ','.join(map("'{}'".format, self.ftypes_fwd)),
        )

        for i in db.query(sql):
            yield self.ftypes_fwd[i.forms]

    def refine(self, values):
        return '{} IN ({})'.format(
            self._column,
            ', '.join("'{}'".format(self.ftypes_rev[x]) for x in values),
        )

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

# class RangeWidget(Widget):
#     pass

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
        ('llm', SummaryWidget),
        ('llm', PointsWidget),
    )

    def __init__(self, db):
        self.db = db
        self.chat = ChatInterface()
        self.widgets = [
            WidgetHolder(x, y(self.db)) for (x, y) in self._widgets
        ]

    def __call__(self, *args):
        logging.warning(args)
        where = ' AND '.join(x.refine(y) for (x, y) in zip(self['sql'], args))
        sql = f'''
        SELECT DISTINCT remarks_qualitative
        FROM {self.db._table}
        WHERE {where}'''

        remarks = (x.remarks_qualitative for x in self.db.query(sql))
        if not remarks:
            return 'No remarks to summarize!'

        widgets = list(self['llm'])
        n = len(widgets)
        (summary, points) = (x.refine(y) for (x, y) in zip(widgets, args[-n:]))

        return self.chat(remarks, summary, points)

    def __iter__(self):
        for i in self.widgets:
            yield i.widget

    def __getitem__(self, item):
        for i in self.widgets:
            if i.wtype == item:
                yield i.widget

#
#
#
config = ConfigParser()
config.read(os.getenv('DB_INI_CONFIG'))
kwargs = config.defaults()
db = DatabaseManager(**kwargs)

fn = Orchestrator(db)
inputs = [ x.build() for x in fn ]
demo = gr.Interface(
    fn=fn,
    inputs=inputs,
    outputs=[
        gr.Textbox(),
    ],
    allow_flagging='never',
)

if __name__ == "__main__":
    demo.queue().launch()
