# coding: utf-8
# !/usr/bin/python

"""
Project: simulator
Tue Jul 12 23:30:48 2016
"""

# Author
__author__ = 'Jason Xing Zhang'
__email__ = 'xingz@uvic.ca'

class ParametersError(Exception):
    """
    Parameter Error class
    """
    def __init__(self, error):
        """
        initialization

        Args:
            error (str): error message
        """
        super(ParametersError, self).__init__(error)


