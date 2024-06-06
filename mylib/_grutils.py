import json
import functools as ft
from pathlib import Path
from datetime import datetime
from tempfile import NamedTemporaryFile

import gradio as gr

class JSONLogger(gr.FlaggingCallback):
    def setup(self, components, flagging_dir):
        self.components = [ x.label for x in components ]
        self.flagging_dir = Path(flagging_dir)
        self.flagging_dir.mkdir(parents=True, exist_ok=True)

    def flag(self, flag_data, flag_option, username):
        record = {
            'date': datetime.now().strftime('%c'),
            'flag_option': flag_option,
        }
        record.update(zip(self.components, flag_data))

        with NamedTemporaryFile(
                mode='w',
                suffix='.json',
                prefix='',
                dir=self.flagging_dir,
                delete=False,
        ) as fp:
            print(json.dumps(record, indent=2), file=fp)
