import json
import functools as ft
from pathlib import Path
from tempfile import mkdtemp
from datetime import datetime

import gradio as gr

class JSONLogger(gr.FlaggingCallback):
    def setup(self, components, flagging_dir):
        self.components = [ x.label for x in components ]
        self.flagging_dir = Path(flagging_dir)

    def flag(self, flag_data, flag_option, username):
        record = {
            'date': datetime.now().strftime('%c'),
            'flag_option': flag_option,
        }
        record.update(zip(self.components, flag_data))

        parent = Path(mkdtemp(dir=self.flagging_dir))
        with parent.joinpath('record').open('w') as fp:
            print(json.dumps(record, indent=2), file=fp)
