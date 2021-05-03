from __future__ import absolute_import

import platform
import errno


if platform.system() == 'Windows':
    blocking_io_errors = set((errno.EWOULDBLOCK,))
    connection_errors = set((errno.ECONNABORTED, errno.ECONNRESET,
        errno.EPIPE))
    invalid_argument = errno.WSAEINVAL
else:
    # Default to a unix system.
    invalid_argument = errno.EINVAL
    blocking_io_errors = set((errno.EAGAIN, errno.EINPROGRESS))
    connection_errors = set((errno.ECONNABORTED, errno.ECONNRESET,
        errno.EPIPE, errno.ECONNREFUSED))
