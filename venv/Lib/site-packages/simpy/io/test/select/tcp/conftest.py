import pytest

from simpy.io import select
from simpy.io.network import Protocol
from simpy.io.packet import PacketUTF8


@pytest.fixture()
def env(request):
    env = select.Environment()
    request.addfinalizer(env.close)
    return env


@pytest.fixture()
def socket_type(env, request):
    return select.TCPSocket


@pytest.fixture()
def protocol(env, request):
    return Protocol(env, PacketUTF8, select.TCPSocket)


