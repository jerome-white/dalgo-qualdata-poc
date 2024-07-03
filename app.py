import os
import json
from pathlib import Path
from dataclasses import dataclass

import pandas as pd
import gradio as gr

from mylib import (
    Widget,
    Logger,
    FormWidget,
    JSONLogger,
    DateWidget,
    ChatDisplay,
    PointsWidget,
    ProgramWidget,
    SummaryWidget,
    RemarkDisplay,
    LocationWidget,
)

#
#
#
class DatabaseManager:
    _table = 'prod.classroom_surveys_normalized'
    _remote = 'postgresql://{user}:{password}@{host}?dbname={dbname}'

    def __init__(self, **kwargs):
        self.con = self._remote.format(**kwargs)

    def query(self, sql):
        Logger.debug(' '.join(sql.strip().split()))
        yield from (pd
                    .read_sql_query(sql, con=self.con)
                    .itertuples(index=False))

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
        Logger.info(args)

        where = ' AND '.join(self.refine(*args))
        if where:
            where = f'WHERE {where}'
        sql = f'''
        SELECT DISTINCT(TRIM(remarks_qualitative)) AS remark
        FROM {self.db._table}
        {where}'''

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
                result = i.refine(j).strip()
                if result:
                    yield result

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
    css=Path('style.css'),
    allow_flagging='manual',
    flagging_options=[
        'inaccurate',
        # 'incoherent output',
    ],
    flagging_dir='flagged',
    flagging_callback=JSONLogger(),
)

if __name__ == "__main__":
    kwargs = config.get('gradio') or {}
    demo.queue().launch(**kwargs)
