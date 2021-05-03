import pytest

from simpy.io import async
from simpy.io.network import Protocol
from simpy.io.packet import PacketUTF8


@pytest.fixture()
def env(request):
    env = async.Environment()
    request.addfinalizer(env.close)
    return env


@pytest.fixture()
def socket_type(env, request):
    return async.TCPSocket


@pytest.fixture()
def protocol(env, request):
    return Protocol(env, PacketUTF8, async.TCPSocket)


