import pytest

from simpy.io.test.socket import *
from simpy._compat import PY2

# The SSL implementation seems to buffer incoming and outgoing data completely.
# A buffer overflow does not happen, so remove the test.
del test_buffer_overflow

del test_read_after_close
del test_write_after_close
del test_read_after_peer_close
del test_write_after_peer_close
del test_multiple_connects
del test_close_during_write_with_pending_data

if PY2:
    import sys
    if sys.version_info[:2] == (2, 6):
        # Due bug http://bugs.python.org/issue9729 calls to send() and recv()
        # on unconnected ssl sockets will fail in Python < 2.7.
        del test_uninitialized_read
        del test_unconnected_write
        del test_write_on_accepting_socket_type
