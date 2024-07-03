import sys
import string
import itertools as it
from pathlib import Path
from argparse import ArgumentParser

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, DayLocator

def gather(path):
    letters = set(it.chain.from_iterable([
        ':',
        string.digits,
        string.whitespace,
        string.ascii_letters,
    ]))

    for p in path.iterdir():
        with p.open() as fp:
            for i in fp:
                info = i.find('INFO app.py')
                if info >= 0:
                    chars = filter(lambda x: x in letters, it.islice(i, info))
                    dtime = ''.join(chars).strip()
                    yield pd.to_datetime(dtime)

if __name__ == "__main__":
    arguments = ArgumentParser()
    arguments.add_argument('--logs', type=Path)
    arguments.add_argument('--output', type=Path)
    args = arguments.parse_args()

    y = 'interactions'

    index = list(gather(args.logs))
    data = it.repeat(1, len(index))
    df = (pd
          .DataFrame(data, index=index)
          .resample('D')
          .count()
          .reset_index(names='date')
          .rename(columns={0: y}))

    ax = sns.lineplot(
        x='date',
        y=y,
        data=df,
        marker='o',
        linestyle='dashed',
        linewidth=0.5,
    )
    ax.set_ylabel(f'LLM {y.capitalize()}')
    ax.set_xlabel('')
    ax.grid(visible=True, axis='both', alpha=0.5)

    ax.xaxis.set_major_locator(DayLocator(interval=4))
    ax.xaxis.set_major_formatter(DateFormatter('%d-%b'))

    plt.savefig(args.output, bbox_inches='tight')
