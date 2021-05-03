import sys
import time
import inspect

import pytest
import _pytest

from simpy.core import EmptySchedule
from simpy._compat import PY2


def pytest_pycollect_makeitem(collector, name, obj):
    """Collects all tests with a `env` argument as normal test. By default
    they would be collected as generator tests."""
    if collector.funcnamefilter(name) and hasattr(obj, '__call__'):
        if 'env' in _pytest.compat.getfuncargnames(obj):
            return list(collector._genfunctions(name, obj))


def pytest_pyfunc_call(pyfuncitem):
    testfunction = pyfuncitem.obj
    funcargs = pyfuncitem.funcargs

    if 'env' not in funcargs: return

    env = funcargs['env']
    step = env.step

    # Set the timeout using a mark value.
    if 'timeout' in pyfuncitem.keywords:
        timeout = pyfuncitem.keywords['timeout'].args[0]
    else:
        timeout = 1.

    argspec = inspect.getargspec(env.step)
    if 'timeout' in argspec.args:
        step = lambda: env.step(timeout=timeout)
    else:
        step = env.step

    # Filter argument names.
    args = {}
    for arg in pyfuncitem._fixtureinfo.argnames:
        args[arg] = funcargs[arg]

    if inspect.isgeneratorfunction(testfunction):
        process = env.process(testfunction(**args))

        def test_done(event):
            if hasattr(env, 'close'):
                env.close()

        process.callbacks.append(test_done)

        while process.is_alive:
            try:
                t = time.time()
                step()
                if time.time() - t >= timeout:
                    process._generator.throw(RuntimeError('Timeout'))
            except EmptySchedule as e:
                process._generator.throw(
                        RuntimeError('Simulation completed, but test process '
                                'has not finished yet!'))

        if isinstance(process.value, BaseException):
            raise process.value
    else:
        testfunction(**args)

    return True
