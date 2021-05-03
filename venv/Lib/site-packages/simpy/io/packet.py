from struct import Struct

from simpy.events import Event


Header = Struct('!L')


class Packet(object):
    # TODO blocksize should always be max_packet_size.
    # TODO Never read more data than necessary.
    # TODO Read and write should return packet events.

    def __init__(self, socket, max_packet_size=16384, blocksize=4096,
            encode=None, decode=None):
        self.env = socket.env
        self.socket = socket
        self.max_packet_size = max_packet_size
        self.blocksize = blocksize
        self.encode = encode
        self.decode = decode

        self._read_ev = None
        self._read_buf = b''
        self._read_size = None

        self._write_ev = None
        self._write_buf = b''

    def _wrap(self, event):
        if event.ok:
            event._value = Packet(event._value, self.max_packet_size,
                self.blocksize, self.encode, self.decode)

    def accept(self):
        event = self.socket.accept()
        event.callbacks.append(self._wrap)
        return event

    def bind(self, address):
        return self.socket.bind(address)

    def listen(self, backlog=5):
        return self.socket.listen(backlog)

    def connect(self, address):
        return self.socket.connect(address)

    @property
    def address(self):
        return self.socket.address

    @property
    def peer_address(self):
        return self.socket.address

    def read(self):
        if self._read_ev is not None:
            raise RuntimeError('Already reading')

        event = self._read_ev = Event(self.env)

        if self._read_buf:
            self._read_data(Event(self.env).succeed(b''))
        else:
            self.socket.read(self.blocksize).callbacks.append(self._read_data)

        return event

    def _read_data(self, event):
        if not event.ok:
            event.defused = True
            self._read_ev.fail(event.value)
            self._read_ev = None
            return

        self._read_buf += event.value

        if self._read_size is None and len(self._read_buf) >= Header.size:
            self._read_size = Header.unpack_from(self._read_buf)[0]
            if self._read_size > self.max_packet_size:
                raise ValueError('Packet too large. Allowed %d bytes but '
                        'got %d bytes' % (self.max_packet_size,
                            self._read_size))
            self._read_size += Header.size

        if (self._read_size is not None and
                len(self._read_buf) >= self._read_size):
            packet = self._read_buf[Header.size:self._read_size]
            if self.decode is None:
                self._read_ev.succeed(packet)
            else:
                # TODO Handle errors.
                self._read_ev.succeed(self.decode(packet))
            self._read_buf = self._read_buf[self._read_size:]
            self._read_size = None
            self._read_ev = None
            return

        self.socket.read(self.blocksize).callbacks.append(self._read_data)

    def write(self, packet):
        if self._write_ev is not None:
            raise RuntimeError('Already writing')

        if self.encode is not None:
            packet = self.encode(packet)

        if len(packet) > self.max_packet_size:
            raise ValueError('Packet too large. Allowed %d bytes but '
                    'got %d bytes' % (self.max_packet_size, len(packet)))

        self._write_ev = Event(self.env)
        self._write_buf = Header.pack(len(packet)) + packet
        self.socket.write(self._write_buf).callbacks.append(self._write_data)
        return self._write_ev

    def _write_data(self, event):
        if not event.ok:
            event.defused = True
            self._write_ev.fail(event.value)
            self._write_ev = None
            return

        self._write_buf = self._write_buf[event.value:]

        if not self._write_buf:
            self._write_ev.succeed()
            self._write_ev = None
        else:
            self.socket.write(self._write_buf).callbacks.append(
                    self._write_data)

    def close(self):
        self.socket.close()


class PacketUTF8(Packet):
    def __init__(self, socket, max_packet_size=16384, blocksize=4096):
        Packet.__init__(self, socket, max_packet_size, blocksize,
                str.encode, bytes.decode)
