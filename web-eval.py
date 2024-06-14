import os
import csv
import string
import random
import itertools as it
import functools as ft
from pathlib import Path
from tempfile import NamedTemporaryFile

import flask as fl
from flask_httpauth import HTTPBasicAuth

app = fl.Flask(__name__)
auth = HTTPBasicAuth()

@ft.cache
def whitespacing():
    ws = {
        ' ': ' ',
        '\t': '&nbsp;' * 5,
    }
    for i in string.whitespace:
        ws.setdefault(i, '<br>')

    return ws

def to_html(path):
    text = path.read_text()
    for i in whitespacing().items():
        text = text.replace(*i)

    return text

#
#
#
class JudgementDropdown:
    _options = {
        '': 'Select an option',
        1: 'Incorrect',
        2: 'Decent',
        3: 'Correct',
        4: 'Unsure',
    }

    @ft.cache_property
    def options(self):
        return '\n'.join(self)

    def __iter__(self):
        for (k, v) in self._options.items():
            extra = '' if k else ' selected disabled hidden'
            yield f'<option value="{k}"{extra}>{v}</option>'

    def to_html(self, name):
        return f'<select name="s_{name}">{self.options}</select><br>'

#
#
#
@dataclass
class DalgoLog:
    root: Path
    name: Path

    def __str__(self):
        return str(self.name)

    def load(self):
        path = self.root.joinpath(self.name)
        return to_html(path.read_text())

#
#
#
@dataclass
class Interaction:
    prompt: str
    response: str
    judgement: str

@dataclass
class Response:
    path: Path

    def __iter__(self):
        with gzip.open(self.path, 'r') as fp:
            data = fp.read().decode('utf-8')

        dropdown = JudgementDropdown()
        for i json.loads(data):
            yield Interaction(
                i['prompt'],
                to_html(i['response']),
                dropdown.to_html(i),
            )

class ResponsePicker:
    @ft.cached_property
    def logs(self):
        return list(self)

    def __init__(self, path):
        self.path = path

    def __iter__(self):
        yield from map(ResponseSummary, self.path.rglob('*.json.gz'))

    def pick(self):
        return random.choice(self.logs)

#
#
#
@auth.verify_password
def verify_password(username, password):
    auth = (
        ('username', username),
        ('password', password),
    )

    return all(os.getenv(f'DALGO_{x.upper()}') == y for (x, y) in auth)

@app.route('/')
@auth.login_required
def index():
    (d_logs, d_summaries) = (
        Path(os.getenv(x)) for x in ('DALGO_LOGS', 'DALGO_SUMMARIES')
    )

    picker = ResponsePicker(d_summaries)
    response = picker.pick()
    log_name = response.path.relative_to(d_summaries)

    log = DalgoLog(d_logs, log_name)
    response = PromptResponse(summary, log)

    return fl.render_template(
        'base.html',
        log=log,
        response=response,
    )

if __name__ == '__main__':
    app.run(debug=True, port=12000)
