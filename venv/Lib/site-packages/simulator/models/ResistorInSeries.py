# coding: utf-8
# !/usr/bin/python

"""
Project: simulator
Wed Jul 20 21:50:01 2016
"""

from simulator.models.Model import Model
from simulator.models.Resistor import Resistor

# Author
__author__ = 'Jason Xing Zhang'
__email__ = 'xingz@uvc.ca'

class ResistorInSeries(Model):
    """
    model of two resistors in series
    """
    def __init__(self, value1, value2):
        """
        initialization
        """
        super(ResistorInSeries, self).__init__()
        self.r1 = Resistor(value1)
        self.r2 = Resistor(value2)

    def rule(self, inputs):
        """
        define the rules of the model
        """
        return self.r1(i=inputs['i']) + self.r2(i=inputs['i'])

ris = ResistorInSeries(2, 3)
ris.states_probe('r1')
results = []
for i in range(10):
    results.append(ris(i=i, logger=True))
print results
print ris.probe_results
