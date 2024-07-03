import sys
import string
import itertools as it
from pathlib import Path
from argparse import ArgumentParser

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, DayLocator

def gather(fp):
    letters = set(it.chain.from_iterable([
        ':',
        string.digits,
        string.whitespace,
        string.ascii_letters,
    ]))

    for i in fp:
        info = i.find('INFO app.py')
        if info >= 0:
            chars = filter(lambda x: x in letters, it.islice(i, info))
            dtime = ''.join(chars).strip()
            yield pd.to_datetime(dtime)

if __name__ == "__main__":
    arguments = ArgumentParser()
    arguments.add_argument('--output', type=Path)
    args = arguments.parse_args()

    index = list(gather(sys.stdin))
    data = it.repeat(1, len(index))
    df = (pd
          .Series(data, index=index)
          .resample('D')
          .count())

    ax = df.plot.line(grid=True)
    ax.set_ylabel('Prompt interactions')
    ax.set_xlabel('Date')

    ax.xaxis.set_major_locator(DayLocator())
    ax.xaxis.set_major_formatter(DateFormatter('%a'))

    plt.savefig(args.output, bbox_inches='tight')
