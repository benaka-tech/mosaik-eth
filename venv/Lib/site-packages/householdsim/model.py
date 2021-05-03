"""

"""
import json

import arrow


DATE_FORMAT = ['YYYY-MM-DD HH:mm', 'YYYY-MM-DD HH:mm:ss']
"""Date format used to convert strings to dates."""


class HouseModel:
    """The HouseModel processes and prepares the load profiles and their
    associated meta data to allow and easier access to it.

    """
    def __init__(self, data, lv_grid):
        # Process meta data
        assert next(data).startswith('# meta')
        meta = json.loads(next(data))
        self.start = arrow.get(meta['start_date'], DATE_FORMAT)
        """The start date of the profile data."""
        self.resolution = meta['resolution']
        """The time resolution of the data in minutes."""
        self.unit = meta['unit']
        """The unit used for the load profiles (e.g., *W*)."""
        self.num_profiles = meta['num_profiles']
        """The number of load profiles in the file."""

        # Obtain id lists
        assert next(data).startswith('# id_list')
        id_list_lines = []
        for line in data:
            if line.startswith('# attrs'):
                break
            id_list_lines.append(line)
        id_lists = json.loads(''.join(id_list_lines))
        self.node_ids = id_lists[lv_grid]
        """List of power grid node IDs for which to create houses."""

        # Enable pre-processing of the data
        self._data = self._get_line(data)

        # Obtain static attributes and create list of house info dicts
        attrs = {}
        for attr, *vals in self._data:
            if attr.startswith('# profiles'):
                break
            attrs[attr] = [int(val) for val in vals]

        #: List of house info dicts
        self.houses = [
            {
                'num': i + 1,
                'node_id': n,
                'num_hh': attrs['num_hh'][i % self.num_profiles],
                'num_res': attrs['num_residents'][i % self.num_profiles],
            } for i, n in enumerate(self.node_ids)
        ]

        # Helpers for get()
        self._last_date = None
        self._cache = None

    def get(self, minutes):
        """Get the current load for all houses for *minutes* minutes since
        :attr:`start`.

        If the model uses a 15min resolution and minutes not multiple of 15,
        the next smaller multiple of 15 will be used. For example, if you
        pass ``minutes=23``, you'll get the value for ``15``.

        """
        # Trim "minutes" to multiples of "self.resolution"
        # Example: res=15, minutes=40 -> minutes == 30
        minutes = minutes // self.resolution * self.resolution

        target_date = self.start.shift(minutes=minutes)
        if target_date != self._last_date:
            # If target date not already reached, search data until we find it:
            for date, *values in self._data:
                date = arrow.get(date, DATE_FORMAT)
                if date == target_date:
                    # Found target date, cache results:
                    values = list(map(float, values))
                    self._cache = [values[i % self.num_profiles]
                                   for i, _ in enumerate(self.houses)]
                    self._last_date = date
                    break
            else:
                # We've reached the end of our data file if the for loop
                # normally finishes.
                raise IndexError('Target date "%s" (%s minutes from start) '
                                 'out of range.' % (target_date, minutes))

        return self._cache

    def get_delta(self, date):
        """Get the amount of minutes between *date* and :attr:`start`.

        The date needs to be a strings formated like :data:`DATE_FORMAT`.

        Raise a :exc:`ValueError` if *date* is smaller than :attr:`start`.

        """
        date = arrow.get(date, DATE_FORMAT)
        if date < self.start:
            raise ValueError('date must >= "%s".' %
                             self.start.format(DATE_FORMAT))
        dt = date - self.start
        minutes = (dt.days * 1440) + (dt.seconds // 60)
        return minutes

    def _get_line(self, iterator):
        for line in iterator:
            yield [item.strip() for item in line.split(',')]
