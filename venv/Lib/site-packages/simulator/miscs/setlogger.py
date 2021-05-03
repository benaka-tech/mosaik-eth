# coding: utf-8
# !/usr/bin/python

"""
Project: simulator
Thu Jul 14 00:03:55 2016
"""

import logging
import logging.config
import inspect

# Author
__author__ = 'Jason Xing Zhang'
__email__ = 'xingz@uvic.ca'

def setlogger(form="brief", level="info", tofile='', wt_mode='w'):
    """
    Set logger

    Args:
        form (str): logging format
        level (str): logging level
        tofile (str): filename, empty for not saving
        wt_mode (str): save to new or continue to old

    Returns:
        logger: logger object

    Examples:
        logger = setlogger()

    """
    formats = dict(
        detailed='''%(filename)s > %(funcName)s() > line:%(lineno)d @ %(asctime)s : %(message)s''',
        brief='''@ %(asctime)s : %(message)s'''
    )

    levels = dict(
        notset=logging.NOTSET,
        debug=logging.DEBUG,
        info=logging.INFO,
        warning=logging.WARNING,
        error=logging.ERROR,
        critical=logging.CRITICAL
    )

    stack = inspect.stack()
    if len(stack) >= 2:
        name = stack[1][1]
    else:
        name = stack[0][1]

    manager = logging.Logger.manager
    if name in manager.loggerDict.keys():
        # using existing logger
        logger = manager.loggerDict[name]
    else:
        # creating new logger
        logger = logging.getLogger(name)
        logger.setLevel(levels[level])
        formatter = logging.Formatter(formats[form])
        if not logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(levels[level])
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            if tofile:
                file_handler = logging.FileHandler(tofile, mode=wt_mode)
                file_handler.setLevel(levels[level])
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
    logger.propagate = False
    return logger
