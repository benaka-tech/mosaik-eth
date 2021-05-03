from os.path import dirname, join

import pytest

from householdsim import mosaik


@pytest.mark.parametrize('data_file_ext', ['', '.gz'])
def test_init(data_file_ext):
    sim = mosaik.HouseholdSim()
    sim.init('sid')

    DATA_FILE = join(dirname(__file__), 'data', 'test.data' + data_file_ext)
    entities = sim.create(1, 'ResidentialLoads',
                          sim_start='2014-01-01 00:00:00',
                          profile_file=DATA_FILE,
                          grid_name='eggs')

    assert entities == [{'eid': 'resid_0', 'type': 'ResidentialLoads',
                         'rel': [], 'children': [
        {'eid': 'House_%s' % i, 'type': 'House', 'rel': []}
        for i in range(5)]},
    ]


def test_init_erros():
    sim = mosaik.HouseholdSim()
    sim.init('sid')
    DATA_FILE = join(dirname(__file__), 'data', 'test.data')

    # Profile file not found
    pytest.raises(FileNotFoundError, sim.create, 1, 'ResidentialLoads',
                  sim_start='2014-01-01 00:00:00',
                  profile_file='foobar',
                  grid_name='foo')

    # Create to many instances
    pytest.raises(ValueError, sim.create, 2, 'ResidentialLoads',
                  sim_start='2014-01-01 00:00:00',
                  profile_file=DATA_FILE,
                  grid_name='eggs')

    # Call create() twice
    sim.create(1, 'ResidentialLoads',
               sim_start='2014-01-01 00:00:00',
               profile_file=DATA_FILE,
               grid_name='eggs')
    pytest.raises(ValueError, sim.create, 1, 'ResidentialLoads',
                  sim_start='2014-01-01 00:00:00',
                  profile_file=DATA_FILE,
                  grid_name='eggs')


def test_step_get_data():
    sim = mosaik.HouseholdSim()
    meta = sim.init('sid')
    assert list(sorted(meta['models'].keys())) == ['House', 'ResidentialLoads']
    assert sim.pos_loads == 1

    entities = sim.create(1, 'ResidentialLoads',
                          sim_start='2014-01-01 00:00:00',
                          profile_file=join(dirname(__file__), 'data',
                                            'test.data'),
                          grid_name='spam')
    assert entities == [{'eid': 'resid_0', 'type': 'ResidentialLoads',
                         'rel': [], 'children': [
        {'eid': 'House_0', 'type': 'House', 'rel': []},
        {'eid': 'House_1', 'type': 'House', 'rel': []},
                         ]},
    ]

    ret = sim.step(0)
    assert ret == 15 * 60
    data = sim.get_data({'House_0': ['P_out'], 'House_1': ['P_out']})
    assert data == {
        'House_0': {'P_out': 0},
        'House_1': {'P_out': 1},
    }

    sim.step(15 * 60)
    data = sim.get_data({'House_0': ['P_out'], 'House_1': ['P_out']})
    assert data == {
        'House_0': {'P_out': 1},
        'House_1': {'P_out': 2},
    }


def test_step_with_offset():
    sim = mosaik.HouseholdSim()
    sim.init('init', pos_loads=False)
    assert sim.pos_loads == -1

    sim.create(1, 'ResidentialLoads',
               sim_start='2014-01-01 01:00:00',
               profile_file=join(dirname(__file__), 'data', 'test.data'),
               grid_name='spam')

    next_step = sim.step(0)
    assert next_step == 15 * 60
    data = sim.get_data({'House_0': ['P_out'], 'House_1': ['P_out']})
    assert data == {
        'House_0': {'P_out': -4},
        'House_1': {'P_out': -5},
    }

    pytest.raises(IndexError, sim.step, 90 * 60)
