from os.path import dirname, join

import arrow
import pytest

from householdsim.model import HouseModel


data_file = join(dirname(__file__), 'data', 'test.data')


scenario_a_houses = [
    {'num': 1, 'node_id': 'x', 'num_hh': 1, 'num_res': 2},
    {'num': 2, 'node_id': 'y', 'num_hh': 2, 'num_res': 4},
]
scenario_a_profiles = [list(range(10)), list(range(1, 11))]

scenario_b_houses = [
    {'num': 1, 'node_id': 'a', 'num_hh': 1, 'num_res': 2},
    {'num': 2, 'node_id': 'b', 'num_hh': 2, 'num_res': 4},
    {'num': 3, 'node_id': 'c', 'num_hh': 1, 'num_res': 5},
    {'num': 4, 'node_id': 'd', 'num_hh': 1, 'num_res': 2},
    {'num': 5, 'node_id': 'e', 'num_hh': 2, 'num_res': 4},
]
scenario_b_profiles = [list(range(10)), list(range(1, 11)), list(range(2, 12)),
                       list(range(10)), list(range(1, 11))]


@pytest.fixture
def hm():
    return HouseModel(open(data_file), 'spam')


@pytest.mark.parametrize(['lv_grid', 'res_houses', 'res_profiles'], [
    ('spam', scenario_a_houses, scenario_a_profiles),
    ('eggs', scenario_b_houses, scenario_b_profiles),
])
def test_housemodel_init(lv_grid, res_houses, res_profiles):
    hm = HouseModel(open(data_file), lv_grid)

    assert hm.start == arrow.get('2014-01-01')
    assert hm.resolution == 15
    assert hm.houses == res_houses
    assert hm.unit == 'W'
    assert hm.num_profiles == 3


def test_housemodel_get(hm):
    """Call get() with the same resolution than the data."""
    # We're gonna making 15min steps
    for i in range(10):
        minutes = i * 15
        ret = hm.get(minutes)
        print(minutes, ret)
        assert ret == [minutes // 15, minutes // 15 + 1]

    pytest.raises(IndexError, hm.get, (i + 1) * 15)


def test_housemodel_get_fast(hm):
    """Call get() faster than the data's resolution."""
    # We're gonna making 5min steps
    for i in range(30):
        minutes = i * 5
        ret = hm.get(minutes)
        assert ret == [minutes // 15, minutes // 15 + 1]

    pytest.raises(IndexError, hm.get, (i + 1) * 5)


def test_housemodel_get_slow(hm):
    """Call get() slower than the data's resolution."""
    # We're gonna making 30min steps
    for i in range(5):
        minutes = i * 30
        ret = hm.get(minutes)
        assert ret == [minutes // 15, minutes // 15 + 1]

    pytest.raises(IndexError, hm.get, (i + 1) * 30)


@pytest.mark.parametrize(['date', 'delta'], [
    ('2014-01-03 01:00:00', 2940),
    ('2014-01-01 02:00:00', 120),
    ('2014-01-01 00:00:00', 0),
])
def test_housemodel_get_delta(hm, date, delta):
    minutes = hm.get_delta(date)
    assert minutes == delta


def tets_housemodel_get_delta_error(hm):
    pytest.raises(ValueError, hm.get_delta, '2013-01-01')
