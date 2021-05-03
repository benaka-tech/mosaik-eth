import pytest

from simpy.io import virtual
from simpy.io.network import Protocol
from simpy.io.packet import PacketUTF8


@pytest.fixture()
def env(request):
    return virtual.Environment()


@pytest.fixture()
def socket_type(env, request):
    return virtual.TCPSocket


@pytest.fixture()
def protocol(env, request):
    return Protocol(env, PacketUTF8, virtual.TCPSocket)


