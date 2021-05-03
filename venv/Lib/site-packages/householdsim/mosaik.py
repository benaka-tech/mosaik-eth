import logging

import mosaik_api

import householdsim.model


logger = logging.getLogger('householdsim')

meta = {
    'models': {
        'ResidentialLoads': {
            'public': True,
            'params': [
                'sim_start',  # The start time for the simulation:
                              # 'YYYY-MM-DD HH:ss'
                'profile_file',  # Name of file with household data
                'grid_name',  # Name of the grid to load
            ],
            'attrs': [],
        },
        'House': {
            'public': False,
            'params': [],
            'attrs': [
                'P_out',  # Active power [W]
                'num',  # House number starting at 1
                'node_id',  # ID of node the house has to be connected to
                'num_hh',  # Number of separate households within the house
                'num_res',  # Number of residents per household
            ],
        },
    },
}


def eid(hid):
    return 'House_%s' % hid


class HouseholdSim(mosaik_api.Simulator):
    def __init__(self):
        super().__init__(meta)

        self.model = None
        self.houses_by_eid = {}
        self.pos_loads = None
        self._file_cache = {}
        self._offset = 0
        self._cache = {}

    def init(self, sid, pos_loads=True):
        logger.debug('Loads will be %s numbers.' %
                     ('positive' if pos_loads else 'negative'))
        self.pos_loads = 1 if pos_loads else -1
        return self.meta

    def create(self, num, model, sim_start, profile_file, grid_name):
        if num != 1 or self.model:
            raise ValueError('Can only create one set of houses.')

        logger.info('Creating houses for %s from "%s"' %
                    (grid_name, profile_file))

        if profile_file.endswith('gz'):
            import gzip
            pf = gzip.open(profile_file, 'rt')
        else:
            pf = open(profile_file, 'rt')

        try:
            self.model = householdsim.model.HouseModel(pf, grid_name)
            self.houses_by_eid = {
                eid(i): house for i, house in enumerate(self.model.houses)
            }
        except KeyError:
            raise ValueError('Invalid grid name "%s".' % grid_name)

        # A time offset in minutes from the simulation start to the start
        # of the profiles.
        self._offset = self.model.get_delta(sim_start)

        return [{
            'eid': 'resid_0',
            'type': 'ResidentialLoads',
            'rel': [],
            'children': [{'eid': eid(i), 'type': 'House', 'rel': []}
                         for i, _ in enumerate(self.model.houses)],
        }]

    def step(self, time, inputs=None):
        # "time" is in seconds. Convert to minutes and add the offset
        # if sim start > start date of the profiles.
        minutes = time // 60
        minutes_offset = minutes + self._offset
        cache = {}
        data = self.model.get(minutes_offset)
        for hid, d in enumerate(data):
            d *= self.pos_loads  # Flip sign if necessary
            cache[eid(hid)] = d
        self._cache = cache
        return (minutes + self.model.resolution) * 60  # seconds

    def get_data(self, outputs):
        data = {}
        for eid, attrs in outputs.items():
            data[eid] = {}
            for attr in attrs:
                if attr == 'P_out':
                    val = self._cache[eid]
                else:
                    val = self.houses_by_eid[eid][attr]
                data[eid][attr] = val
        return data


def main():
    return mosaik_api.start_simulation(HouseholdSim(), 'Household simulation')
