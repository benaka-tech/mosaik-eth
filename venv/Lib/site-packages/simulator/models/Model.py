# coding: utf-8
# !/usr/bin/python

"""
Project: simulator
Tue Jul 19 23:59:07 2016
"""

from simulator.miscs.setlogger import setlogger
from simulator.miscs.Parameters import Parameters

# Author
__author__ = 'Jason Xing Zhang'
__email__ = 'xingz@uvic.ca'


class Model(object):
    """
    abstract class for component
    """
    def __init__(self):
        """
        initilization
        """
        self.parameters = Parameters()
        self.logger = setlogger()
        self.outputs = None
        self.probe_results = {}

    def set_states(self, name, ini_value):
        """
        define inputs

        Args:
            name (str): inputs name
            ini_value (num): initial value
        """
        self.__dict__[name] = ini_value

    def set_parameters(self, name, value):
        """
        define parameters, which are CONSTANTS

        Args:
            name (str): parameter name
            value (num): parameter value
        """
        self.parameters.__dict__[name] = value

    def display_stats(self):
        """
        display all states
        """
        return dict(
            [(name, value) for name, value in self.__dict__.iteritems() \
                if name not in ['logger', 'parameters', 'probe_results']]
        )

    def states_probe(self, name):
        """
        set the probe on state with name

        Args:
            name (string): state name
        """
        self.probe_results[name] = []

    def __call__(self, **inputs):
        if 'logger' in inputs.keys() and inputs['logger']:
            self.logger.info("Running {0}.".format(self.__class__.__name__))
        self.outputs = self.rule(inputs)
        for name in self.__dict__.keys():
            if name in self.probe_results.keys():
                if isinstance(self.__dict__[name], Model):
                    self.probe_results[name].append(self.__dict__[name].display_stats())
                else:
                    self.probe_results[name].append(self.__dict__[name])
        return self.outputs
