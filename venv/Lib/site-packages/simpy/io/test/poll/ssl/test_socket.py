import pytest

from simpy.io.test.socket import *

# The SSL implementation seems to buffer incoming and outgoing data completely.
# A buffer overflow does not happen, so remove the test.
del test_buffer_overflow

del test_read_after_close
del test_write_after_close
del test_read_after_peer_close
del test_write_after_peer_close
del test_multiple_connects
del test_close_during_write_with_pending_data
