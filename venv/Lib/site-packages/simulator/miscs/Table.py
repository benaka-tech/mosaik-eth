# coding: utf-8
# !/usr/bin/python

"""
Project: ElecSim
Mon Jul 18 22:10:02 2016
"""

import json
import numpy as np
from elecsim.errors.TableError import TableError

# Author
__author__ = 'Jason Xing Zhang'
__email__ = 'xingz@uvic.ca'

class Table(object):
    """
    Table class

    Examples:

    """
    def __init__(self, axis, data):
        """
        initialize class

        Args:
            axis (list): [[axis1], [axis2], ...]
            data (list): [[d1], [d2], ...]

        Returns: None
        """
        dim = len(axis)
        try:
            subdata = data
            for i in range(0, dim):
                if len(subdata) != len(axis[i]):
                    raise TableError(\
                        " Number of points does NOT match for axis {0}"\
                        .format(i+1)
                    )
                subdata = subdata[0]
        except TypeError:
            raise TableError(\
                "Dimension does NOT match. dim(axis)={0}".format(dim)
            )
        self.axis = axis
        self.data = data

    def __repr__(self):
        """
        when use instance, return the axis and data

        Returns:
            data (dict): {'axis': self.axis, 'data': self.data}

        """
        return "Table: " + str({'axis': self.axis, 'data': self.data})

    def _midpoint(self, dotx, pairs):
        """
        get doty from the line, which goes through dots defined by pairs

        Args:
            dotx (float): x coordinate
            pairs (list): [[x1, x2], [y1, y2]]

        Returns:
            doty (float): y coordinate
        """
        slope = pairs[0][0]-pairs[0][1]
        if slope == 0:
            raise TableError(\
                "Found zero slope, wrong data {0} in axis definition."\
                .format(pairs[0])
            )
        else:
            slope = (pairs[1][0]-pairs[1][1])/slope
            return (dotx - pairs[0][0]) * slope + pairs[1][0]

    def __getitem__(self, *args):
        """
        get table value

        Args:
            args (list): index

        Returns:
            value (float): table value
        """
        args = args[0]
        if isinstance(args, float) or isinstance(args, int):
            args = (args,)
        if len(args) != len(self.axis):
            raise TableError(\
                "Table dimension is {0}, but {1} indices here"\
                .format(len(self.axis), len(args))
            )
        else:
            return self._nd(args, self.data, 0)

    def _nd(self, idx, table, n):
        """
        call itself to interpolate n dimensional table
        :param idx: idx from function lookup
        :param table: table for each dimension
        :param n: dimension
        :return: value
        """
        nb = self._get_neighbour(idx[n], n)
        if n == len(self.axis)-1:
            data = [[nb[0][0], nb[1][0]],[table[nb[0][1]], table[nb[1][1]]]]
        else:
            data = [[nb[0][0], nb[1][0]],\
                    [self._nd(idx, table[nb[0][1]], n+1), self._nd(idx, table[nb[1][1]], n+1)]]
        return self._midpoint(idx[n], data)

    def _get_neighbour(self, dot, n):
        """
        get neighbours for dot

        Args:
            dot (float): axis dot
            n (int): nth dimensional axis

        Returns:
            [left, index of left], [right, index of right]
        """
        axis = self.axis[n]
        if max(axis) < dot:
            return [axis[-2], len(axis)-2], [axis[-1], len(axis)-1]
        elif min(axis) > dot:
            return [axis[0], 0], [axis[1], 1]
        else:
            left = max([i for i in axis if i < dot])
            right = min([i for i in axis if i > dot])
            return [left, axis.index(left)], [right, axis.index(right)]

