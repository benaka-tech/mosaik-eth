#   coding: utf-8 
#   !/usr/bin/python
#   For Project - CalculateEng

# Version - 0.0 || August 28, 2015 || 8:44 PM


import linear_inter_1d
import lookup_table
import setlogger


__author__ = "Jason Xing Zhang"
__email__ = "jason.xing.zhang@gmail.com"


logger = setlogger.setlogger()

def test_linear_inter_1d():
    data = [[1, 1], [2, 2]]
    x = 9
    y = linear_inter_1d.linear_inter_1d(x, data)
    logger.info("y is %f", y)


def test_lookup_table():
    table2 = lookup_table.LookupTable("table.json")
    print table2.lookup([1.5, 1.5, 0.15])


test_linear_inter_1d()
test_lookup_table()
