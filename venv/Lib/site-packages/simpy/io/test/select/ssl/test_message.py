import pytest

from simpy.io.test.message import *
from simpy._compat import PY2


del test_server_close

if PY2:
    import sys
    if sys.version_info[:2] == (2, 6):
        # Due bug http://bugs.python.org/issue9729 calls to send() and recv()
        # on unconnected ssl sockets will fail in Python < 2.7.
        del test_unconnected_recv
        del test_unconnected_send
