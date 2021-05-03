# coding: utf-8
# !/usr/bin/python

"""
Project: simulator
Mon Jul 11 22:44:55 2016
"""

from simulator.errors.ParametersError import ParametersError

# Author
__author__ = 'Jason Xing Zhang'
__email__ = 'xingz@uvic.ca'

class Parameters(object):
    """
    Parameter object
    """
    def __init__(self):
        """
        pass
        """
        pass

    def __setattr__(self, name, value):
        """
        if any parameter's value is about to be changed, raise an error
        """
        if name in self.__dict__.keys():
            raise ParametersError(\
                    "Can't change parameter {0} = {1}, which is a constant."\
                    .format(name, str(value))
                )
        else:
            raise ParametersError( \
                    "Can't add parameter {0}. Please add it in 'Parameters*.py' file"\
                    .format(name)
                )

