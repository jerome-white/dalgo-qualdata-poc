import sys
import string
import itertools as it
from pathlib import Path
from argparse import ArgumentParser

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, DayLocator

class MetricPlotter:
    def __init__(self, df, y, ylabel, **kwargs):
        self.df = df
        self.y = y
        self.ylabel = ylabel
        self.kwargs = kwargs

    def plot(self, ax):
        sns.lineplot(
            x='date',
            y=self.y,
            data=self.df,
            ax=ax,
            **self.kwargs,
        )
        ax.set_xlabel('')
        ax.set_ylabel(self.ylabel)
        ax.grid(visible=True, axis='both', alpha=0.5)

class DailyUsagePlotter(MetricPlotter):
    def __init__(self, df):
        view = (df
                .set_index('date')
                .resample('D')
                .count()
                .reset_index())
        super().__init__(
            view,
            'usage',
            'LLM Interactions',
            marker='o',
            linestyle='dashed',
            linewidth=0.5,
        )

class CumulativeUsagePlotter(MetricPlotter):
    @staticmethod
    def aggregator(x):
        return x['usage'].cumsum()

    def __init__(self, df):
        y = 'aggregate'
        view = (df
                .sort_values(by='date')
                .assign(**{y: self.aggregator}))
        ylabel = f'{y.capitalize()} usage'
        super().__init__(view, y, ylabel)

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
                    yield {
                        'date': pd.to_datetime(dtime),
                        'usage': 1,
                    }

if __name__ == "__main__":
    arguments = ArgumentParser()
    arguments.add_argument('--logs', type=Path)
    arguments.add_argument('--output', type=Path)
    args = arguments.parse_args()

    df = pd.DataFrame.from_records(gather(args.logs))
    plotters = list(map(lambda x: x(df), (
        DailyUsagePlotter,
        CumulativeUsagePlotter,
    )))
    nrows = len(plotters)

    (_, axes) = plt.subplots(nrows=nrows, sharex=True)
    for (i, (p, ax)) in enumerate(zip(plotters, axes), 1):
        p.plot(ax)
        if i == nrows:
            ax.xaxis.set_major_locator(DayLocator(interval=4))
            ax.xaxis.set_major_formatter(DateFormatter('%d-%b'))

    plt.savefig(args.output, bbox_inches='tight')
