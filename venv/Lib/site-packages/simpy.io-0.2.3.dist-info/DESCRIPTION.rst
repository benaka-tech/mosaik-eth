simpy.io
========

*simpy.io* is an asynchronous networking library based on SimPy_. The nature
of networking is thoroughly event-based (messages can for example be thought of
as events). *simpy.io* marries the solid event system of SimPy_ with
asynchronous input and output.

It provides several degrees of abstraction (raw sockets, packets and
request-reply messages), supports various back-ends ((e)poll, select, asyncore,
virtual) and lets you use different socket types, like TCP, SSL-encrypted,
simulated). Furthermore protocols like HTTP, WebSockets and an extensible RPC
interface are also supported.

.. _SimPy: http://simpy.readthedocs.org

Current status
--------------

simpy.io is currently in the early alpha phase of development. There is no
guarantee for API stability (modules will almost certainly be renamed before
the 1.0 release) and simpy.io may break on your system. Sadly, there isn't any
documentation available as of now (apart from the examples and tests).

The state of the individual modules is as follows:

* sockets: stable *alpha*
* packets: stable *alpha*
* message: stable *alpha*
* http: *draft*
* websockets: *draft*
* rpc: *draft*

The following table represents the support matrix. As of now, there's no CI
system in place to guarantee the test stability, yet.

======== =============== ============= ========== ================
System   Flavor          Python        Backends   Successful tests
======== =============== ============= ========== ================
Linux    ArchLinux       2.6.9, 2.7.6, *all*      *all*
                         3.3, 3.4
Linux    Ubuntu (12.04)  2.6.9, 2.7.6, *all*      *most*
                         3.3
Windows  Windows 7       2.6.9, 2.7.6, select     *all*
                         3.3
OS X     Maverick (10.9) 3.3           *no* epoll *most*
======== =============== ============= ========== ================

.. note::

    Python 2 does not natively support all of SimPy's features (e.g. no
    exception chains or return statements inside of generators) but workarounds
    are available.

Installation
------------

simpy.io requires Python 2.7 or 3.3 and SimPy 3. You can install it from
Bitbucket via pip:

.. sourcecode:: bash

    $ pip install hg+https://bitbucket.org/simpy/simpy.io

Examples
--------

The following three examples demonstrate simpy.io's levels of abstraction:

Socket level
^^^^^^^^^^^^

When working directly with simpy.io sockets, you can try to *read* and *write*
a specified number of bytes from or to a socket (note that there is no
guarantee from the OS that all data will be received or transmitted):

.. sourcecode:: python

    >>> from simpy.io import select as backend
    >>>
    >>> def server(env, addr):
    ...     server_sock = backend.TCPSocket.server(env, addr)
    ...     sock = yield server_sock.accept()
    ...     data = yield sock.read(4)
    ...     print(data.decode())
    ...     yield sock.write('cya'.encode())
    >>>
    >>> def client(env, addr):
    ...     sock = backend.TCPSocket.connection(env, addr)
    ...     yield sock.write('ohai'.encode())
    ...     data = yield sock.read(3)
    ...     print(data.decode())
    >>>
    >>> addr = ('127.0.0.1', 5555)
    >>> env = backend.Environment()
    >>> srv = env.process(server(env, addr))
    >>> cli = env.process(client(env, addr))
    >>> env.run(until=cli)
    ohai
    cya


Packet level
^^^^^^^^^^^^

simpy.io packets alleviate the limitation of raw sockets and allow you to read
and write complete packets. These can either be bytes (if you use ``Packet``)
or (unicode) strings (if you use ``PacketUTF8``):

.. sourcecode:: python

    >>> from simpy.io import select as backend
    >>> from simpy.io.packet import Packet
    >>>
    >>> def server(env, addr):
    ...     server_sock = backend.TCPSocket.server(env, addr)
    ...     sock = yield server_sock.accept()
    ...     packet = Packet(sock)
    ...     data = yield packet.read()
    ...     print(data.decode())
    ...     yield packet.write('cya'.encode())
    >>>
    >>> def client(env, addr):
    ...     packet = Packet(backend.TCPSocket.connection(env, addr))
    ...     yield packet.write('ohai'.encode())
    ...     data = yield packet.read()
    ...     print(data.decode())
    >>>
    >>> addr = ('127.0.0.1', 5556)
    >>> env = backend.Environment()
    >>> srv = env.process(server(env, addr))
    >>> cli = env.process(client(env, addr))
    >>> env.run(until=cli)
    ohai
    cya


Message level
^^^^^^^^^^^^^

The message level adds message counters that allow you to asynchronously send
messages (even concurrently) and maps replies to their proper requests.
Furthermore, you can specify (de)serializers (by default, *JSON* is used) and
replies can signal success/failure:

.. sourcecode:: python

    >>> from simpy.io import select as backend
    >>> from simpy.io.packet import PacketUTF8
    >>> from simpy.io.message import Message
    >>>
    >>> def server(env, addr):
    ...     server_sock = backend.TCPSocket.server(env, addr)
    ...     sock = yield server_sock.accept()
    ...     message = Message(env, PacketUTF8(sock))
    ...     request = yield message.recv()
    ...     print(request.content)
    ...     yield request.succeed('cya')
    >>>
    >>> def client(env, addr):
    ...     message = Message(env, PacketUTF8(
    ...             backend.TCPSocket.connection(env, addr)))
    ...     reply = yield message.send('ohai')
    ...     print(reply)
    >>>
    >>> addr = ('127.0.0.1', 5557)
    >>> env = backend.Environment()
    >>> srv = env.process(server(env, addr))
    >>> cli = env.process(client(env, addr))
    >>> env.run(until=cli)
    ohai
    cya

Help & Contact
--------------

Please feel free to post a message to the `SimPy-Users mailing list`__ to ask
for help or to discuss the ongoing development. Bugs should be posted on our
`issue tracker`__ here on BitBucket.

__ mailto:simpy-users@lists.sourceforge.net
__ https://bitbucket.org/simpy/simpy.io/issues?status=new&status=open


