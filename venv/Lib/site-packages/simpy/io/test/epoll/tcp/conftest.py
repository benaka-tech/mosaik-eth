import pytest

from simpy.io import poll
from simpy.io.network import Protocol
from simpy.io.packet import PacketUTF8


@pytest.fixture()
def env(request):
    env = poll.Environment(type='epoll')
    request.addfinalizer(env.close)
    return env


@pytest.fixture()
def socket_type(env, request):
    return poll.TCPSocket


@pytest.fixture()
def protocol(env, request):
    return Protocol(env, PacketUTF8, poll.TCPSocket)
