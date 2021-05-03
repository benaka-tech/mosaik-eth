# coding: utf-8
# !/usr/bin/python

"""
Project: simulator
Wed Jul 20 00:07:48 2016
"""

from simulator.models.Model import Model

# Author
__author__ = 'Jason Xing Zhang'
__email__ = 'xingz@uvic.ca'


class Resistor(Model):
    """
    model of a resistor
    """
    def __init__(self, value):
        """
        initialization

        Args:
            value (num): resistor value
        """
        super(Resistor, self).__init__()
        self.set_parameters('r', value)

    def rule(self, inputs):
        """
        define the relation between inputs and outputs

        Args:
            inputs(dict): {input_name: input_value}
        """
        return self.parameters.r * inputs['i']

