import itertools as it

import gradio as gr

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
