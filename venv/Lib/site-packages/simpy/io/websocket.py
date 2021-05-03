import os
import random
import hashlib
from base64 import b64encode
import struct
import re
import errno

from simpy._compat import PY2
from simpy.core import Event
from simpy.io.network import socket_error


frame_headers = [
    [ # Server frame headers.
        struct.Struct('!BB'),
        struct.Struct('!BBH'),
        struct.Struct('!BBQ') # Mmh, steaks!
    ],
    [ # Client frame headers.
        struct.Struct('!BB4s'),
        struct.Struct('!BBH4s'),
        struct.Struct('!BBQ4s'),
    ],
]

class WSRead(Event):
    def __init__(self, socket):
        Event.__init__(self, socket.env)
        self.socket = socket


class WSWrite(Event):
    def __init__(self, socket, data):
        Event.__init__(self, socket.env)
        self.socket = socket
        self.data = data


def parse_header_data(header_data):
    header_data = header_data.decode('iso-8859-1')

    headers = {}
    for line in header_data.split('\r\n')[1:]:
        name, value = line.split(':', 1)
        headers[name.strip()] = value.strip()
    return headers


class WebSocket(object):
    def __init__(self, socket, blocksize=4096):
        self.env = socket.env
        self.socket = socket
        self.blocksize = blocksize
        self._read_ev = self.env.event()
        self._write_ev = self.env.event()

    def compute_accept_key(self, key):
        sha = hashlib.new('sha1')
        sha.update(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11')
        return b64encode(sha.digest())

    def configure(self, initiate, headers=None, uri=None):
        self.peer_address = '%s:%d' % self.socket.address
        if not initiate:
            return self.env.process(self._server_handshake(headers))
        else:
            return self.env.process(self._client_handshake(uri))

    def _server_handshake(self, headers, data=b''):
        if headers is None:
            while True:
                idx = data.find(b'\r\n\r\n')
                if idx >= 0: break
                data += yield self.socket.read(self.blocksize)

            header_data, data = data[:idx], data[idx+4:]
            headers = parse_header_data(header_data)

        try:
            version = int(headers['Sec-WebSocket-Version'])

            if version != 13:
                raise RuntimeError('Unsupported version %d' % version)
        except KeyError:
            pass

        key = headers['Sec-WebSocket-Key'].strip()

        accept_key = self.compute_accept_key(key.encode('iso-8859-1'))

        yield self.socket.write(b'HTTP/1.1 101 Switching Protocols\r\n'
                b'Upgrade: websocket\r\n'
                b'Connection: Upgrade\r\n'
                b'Sec-WebSocket-Accept: ' + accept_key +
                b'\r\n\r\n')

        self._reader_proc = self.env.process(self._reader(data, mask=True))
        self._writer_proc = self.env.process(self._writer(mask=False))

    def _client_handshake(self, uri):
        # TODO Is it possible to create a random byte sequence directly?
        key = bytearray(b' ' * 16)
        for i in range(len(key)):
            key[i] = random.randint(0, 255)
        key = b64encode(bytes(key))

        statusline = 'GET %s HTTP/1.1\r\n' % uri
        headers = [
                ('Host', self.peer_address),
                ('Upgrade', 'websocket'),
                ('Connection', 'websocket'),
                ('Sec-WebSocket-Key', key.decode('iso-8859-1')),
                ('Sec-WebSocket-Version', 13),
        ]
        headers = '\r\n'.join(['%s: %s' % header for header in headers])
        yield self.socket.write(
                (statusline + headers + '\r\n\r\n').encode('iso-8859-1'))

        data = b''
        while True:
            idx = data.find(b'\r\n\r\n')
            if idx >= 0: break
            data += yield self.socket.read(self.blocksize)

        header_data, data = data[:idx], data[idx+4:]
        headers = parse_header_data(header_data)

        # Check the accept key.
        accept_key = self.compute_accept_key(key).decode('iso-8859-1')
        if headers['Sec-WebSocket-Accept'] != accept_key:
            raise RuntimeError('WebSocket accept key mismatch')

        self._reader_proc = self.env.process(self._reader(data, mask=False))
        self._writer_proc = self.env.process(self._writer(mask=True))

    def _reader(self, data=b'', mask=False):
        try:
            read = self.socket.read
            blocksize = self.blocksize
            headers = frame_headers[mask]
            while True:
                event = None
                event = yield self._read_ev
                self._read_ev = self.env.event()

                while len(data) < headers[0].size:
                    data += yield read(4096)

                # Parse header.
                header = bytearray(data[:headers[0].size])
                opcode = header[0]
                if mask and not header[1] & 0x80:
                    raise RuntimeError('Masking bit was not set')

                length_desc = 0x7f & header[1]
                if length_desc == 126:
                    while len(data) < headers[1].size:
                        data += yield read(blocksize)
                    header = headers[1].unpack(data[:headers[1].size])
                    data = data[headers[1].size:]
                    size = header[2]
                elif length_desc == 127:
                    while len(data) < headers[2].size:
                        data += yield read(blocksize)
                    header = headers[2].unpack(data[:headers[2].size])
                    data = data[headers[2].size:]
                    size = header[2]
                else:
                    header = headers[0].unpack(data[:headers[0].size])
                    data = data[headers[0].size:]
                    size = header[1] & 0x7f

                # Read packet.
                while len(data) < size:
                    data += yield read(blocksize)
                packet, data = data[:size], data[size:]

                if mask:
                    # Unmask data.
                    # TODO Is it possible to unmask the data using a builtin
                    # function?
                    if PY2:
                        maskingkey = bytearray(header[-1])
                    else:
                        maskingkey = header[-1]

                    packet = bytearray(packet)
                    for i in range(size):
                        packet[i] ^= maskingkey[i % 4]
                    packet = bytes(packet)

                # Convert packet data if necessary.
                if opcode & 0x7f == 1:
                    packet = packet.decode()
                elif opcode & 0x7f == 2:
                    pass
                elif opcode & 0x7f == 8:
                    # Close connection.
                    # FIXME Should I really send the close control frame?
                    self.socket.close()
                    raise socket_error(errno.ECONNRESET)
                else:
                    raise RuntimeError('Unsupported opcode %x' % opcode)

                event.succeed(packet)
        except BaseException as e:
            # FIXME Add proper error handling.
            self._reader_proc.defused = True
            if event is not None:
                event.fail(e)

    def _writer(self, mask=False):
        try:
            write = self.socket.write
            headers = frame_headers[mask]
            while True:
                event = None
                event = yield self._write_ev
                self._write_ev = self.env.event()

                # Select a masking key.
                maskingkey = os.urandom(4)

                # Determine packet type.
                if type(event.data) is bytes:
                    opcode = 2
                    data = event.data
                else:
                    opcode = 1
                    data = event.data.encode()

                # Always set the FIN flag.
                opcode |= 0x80

                # Build frame header.
                if len(data) < 126:
                    args = (opcode, len(data) | (0x80 if mask else 0))
                    header = headers[0]
                elif len(data) < 2**16:
                    args = (opcode, 126 | (0x80 if mask else 0), len(data))
                    header = headers[1]
                else:
                    args = (opcode, 127 | (0x80 if mask else 0), len(data))
                    header = headers[2]

                if mask:
                    args += (maskingkey,)
                    header = header.pack(*args)

                    # Mask data.
                    data = bytearray(data)

                    if PY2:
                        maskingkey = bytearray(maskingkey)

                    # TODO Figure out if there is a more performant masking
                    # scheme.
                    for i in range(len(data)):
                        data[i] ^= maskingkey[i % 4]
                else:
                    header = header.pack(*args)

                # FIXME Only SSL on Python 2.6 requires transformation of the
                # data into bytes.
                data = bytes(header + data)
                while data:
                    sent = yield write(data)
                    data = data[sent:]
                event.succeed()
        except BaseException as e:
            # FIXME Add proper error handling.
            self._writer_proc.defused = True
            if event is not None:
                event.fail(e)

    def read(self):
        event = WSRead(self)
        self._read_ev.succeed(event)
        return event

    def write(self, data):
        event = WSWrite(self, data)
        self._write_ev.succeed(event)
        return event


class WebSocketHixie(object):
    key_data = struct.Struct('!II8s')
    noise = list(range(0x0021, 0x002f)) + list(range(0x003a, 0x007e))
    packet_headerfooter = struct.Struct('!B')

    def __init__(self, socket, origin, location, blocksize=4096):
        self.env = socket.env
        self.socket = socket
        self.origin = origin
        self.location = location
        self.blocksize = blocksize
        self._read_ev = self.env.event()
        self._write_ev = self.env.event()

    def configure(self, initiate, headers=None, uri=None, excess_data=b''):
        self.peer_address = '%s:%d' % self.socket.address
        if not initiate:
            return self.env.process(
                    self._server_handshake(headers, excess_data))
        else:
            return self.env.process(self._client_handshake(uri, excess_data))

    def _server_handshake(self, headers, data=b''):
        if headers is None:
            data = b''
            while True:
                idx = data.find(b'\r\n\r\n')
                if idx >= 0: break
                data += yield self.socket.read(self.blocksize)

            header_data, data = data[:idx], data[idx+4:]
            headers = parse_header_data(header_data)

        key_1 = headers['Sec-WebSocket-Key1']
        key_2 = headers['Sec-WebSocket-Key2']
        number_1 = (int(''.join(re.findall('\d', key_1))) //
                int(len(re.findall(' ', key_1))))
        number_2 = (int(''.join(re.findall('\d', key_2))) //
                int(len(re.findall(' ', key_2))))

        # Read final eight byte data.
        while len(data) < 8:
            data += yield self.socket.read(8 - len(data))

        m = hashlib.md5()
        m.update(self.key_data.pack(number_1, number_2, data[:8]))
        accept_key = m.digest()

        origin = self.origin.encode('iso-8859-1')
        location = self.location.encode('iso-8859-1')

        handshake = (b'HTTP/1.1 101 Switching Protocols\r\n' +
                b'Upgrade: websocket\r\n' +
                b'Connection: Upgrade\r\n' +
                b'Sec-WebSocket-Origin: ' + origin + b'\r\n' +
                b'Sec-WebSocket-Location: ' + location + b'\r\n\r\n' +
                accept_key)
        while handshake:
            sent = yield self.socket.write(handshake)
            handshake = handshake[sent:]

        self.env.process(self._reader_proc())
        self.env.process(self._writer_proc())

    def _generate_random_key(self):
        spaces = random.randint(1, 12)
        number = random.randint(0, 4294967295 // spaces)
        key = [c for c in str(number * spaces)]

        for i in range(random.randint(1, 12)):
            key.insert(random.randint(0, len(key) - 1),
                    chr(random.choice(self.noise)))

        for i in range(spaces):
            key.insert(random.randint(1, len(key) - 2), ' ')

        return number, ''.join(key)

    def _client_handshake(self, uri, data=b''):
        number_1, key_1 = self._generate_random_key()
        number_2, key_2 = self._generate_random_key()
        key_3 = bytearray(b' ' * 8)
        for i in range(len(key_3)):
            key_3[i] = random.randint(0, 255)
        key_3 = bytes(key_3)

        # Calculate the md5sum of the final key.
        m = hashlib.md5()
        m.update(self.key_data.pack(number_1, number_2, bytes(key_3)))
        accept_key = m.digest()

        statusline = 'GET %s HTTP/1.1\r\n' % uri
        headers = [
                ('Host', self.peer_address),
                ('Upgrade', 'WebSocket'),
                ('Connection', 'Upgrade'),
                ('Sec-WebSocket-Key1', key_1),
                ('Sec-WebSocket-Key2', key_2),
        ]
        headers = '\r\n'.join(['%s: %s' % header for header in headers])
        handshake = ((statusline + headers).encode('iso-8859-1') +
                b'\r\n\r\n' + key_3)

        while handshake:
            sent = yield self.socket.write(handshake)
            handshake = handshake[sent:]

        while True:
            idx = data.find(b'\r\n\r\n')
            if idx >= 0: break
            data += yield self.socket.read(self.blocksize)

        header_data, data = data[:idx], data[idx+4:]

        while len(data) < 16:
            data += yield self.socket.read(16 - len(data))

        if data != accept_key:
            raise RuntimeError('Websocket key mismatch')

        self.env.process(self._reader_proc(data[16:]))
        self.env.process(self._writer_proc())

    def _reader_proc(self, data=b''):
        read = self.socket.read
        blocksize = self.blocksize
        packet_footer = self.packet_headerfooter.pack(0xff)
        while True:
            event = None
            event = yield self._read_ev
            self._read_ev = self.env.event()

            try:
                while len(data) < 2:
                    data += yield read(self.blocksize)

                # Parse header.
                header = bytearray(data[:2])
                opcode = header[0]
                if header[0] & 0x80:
                    raise RuntimeError('Length indicated packages not '
                            'supported yet')
                data = data[1:]

                # Read packet.
                idx = 0
                while True:
                    idx = data.find(packet_footer, idx)
                    if idx > 0: break
                    idx = len(data)
                    data += yield read(blocksize)
                packet, data = data[:idx], data[idx+1:]
                event.succeed(packet)
            except BaseException as e:
                if event is not None:
                    event.fail(e)


    def _writer_proc(self):
        write = self.socket.write
        packet_header = self.packet_headerfooter.pack(0x00)
        packet_footer = self.packet_headerfooter.pack(0xff)

        while True:
            event = None
            event = yield self._write_ev
            self._write_ev = self.env.event()

            # Determine packet type.
            if type(event.data) is str:
                data = packet_header + event.data.encode() + packet_footer
            elif type(event.data) is bytes:
                data = packet_header + event.data + packet_footer
            else:
                raise RuntimeError('Invalid data %s' % event.data)

            try:
                while data:
                    sent = yield write(data)
                    data = data[sent:]
            except BaseException as e:
                if event is not None:
                    event.fail(e)
                return
            event.succeed()

    def read(self):
        event = WSRead(self)
        self._read_ev.succeed(event)
        return event

    def write(self, data):
        event = WSWrite(self, data)
        self._write_ev.succeed(event)
        return event
