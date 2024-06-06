import itertools as it
from string import Template
from pathlib import Path

from openai import OpenAI, BadRequestError

from ._logutils import Logger

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
        Logger.debug(user_prompt)

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
