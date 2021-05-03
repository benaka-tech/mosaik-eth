import os
from types import GeneratorType
import socket
import types
import errno
from itertools import count
from collections import deque

try:
    from html import escape
except ImportError:
    from cgi import escape

from simpy.events import Event, Interrupt
from simpy.io.network import socket_error
from simpy.io.broker import RPC

from simpy._compat import PY2

if not PY2:
    from http.client import HTTPException
else:
    from httplib import HTTPException

# TODO Add a codec for query arguments.
# TODO The codec should also encode the return value.
# TODO Websocket upgrade.


class InMessage(Event):
    def __init__(self, channel):
        Event.__init__(self, channel.env)
        self.channel = channel

        # FIXME This sould be removed.
        self.respond = types.MethodType(OutResponse, channel)

        self.read = types.MethodType(Read, self)
        self._read_ev = self.env.event()

        try:
            channel._recv_queue.append(self)
        except:
            if (hasattr(channel, '_recv_queue') and
                    channel._recv_queue is not None):
                raise

            raise channel._reader_process.value

        if channel._in_message_ev is not None:
            channel._in_message_ev.succeed(self)
            channel._in_message_ev = None

    def parse_header(self, data):
        try:
            # Decode byte sequences to strings and split by lines.
            header_lines = data.decode('iso-8859-1').split('\r\n')

            self.headers = {}

            # Skip startline.
            for line in header_lines[1:]:
                key, value = line.split(':', 1)
                self.headers[key.strip()] = value.strip()

            self.parse_startline(header_lines[0])
            return
        except:
            pass

        raise HTTPException('Malformed header:\n%s' % data.decode(
                'utf-8', 'replace'))

    def data(self):
        return self.read(all=True)


class OutMessage(Event):
    def __init__(self, channel, statusline, headers=None, data=None):
        Event.__init__(self, channel.env)

        self.channel = channel
        self.statusline = statusline
        self.headers = headers if headers is not None else {}

        self.write = types.MethodType(Write, self)
        self._write_ev = self.env.event()

        if data is not None:
            self.headers['Content-Length'] = str(len(data))
            self.write(data)
        else:
            self.headers['Transfer-Encoding'] = 'chunked'

        try:
            channel._send_queue.append(self)
        except:
            if (hasattr(channel, '_send_queue') and
                    channel._send_queue is not None):
                raise

            raise channel._writer_process.value

        if channel._out_message_ev is not None:
            channel._out_message_ev.succeed(self)
            channel._out_message_ev = None


class Read(Event):
    def __init__(self, message, all=False):
        Event.__init__(self, message.env)

        try:
            if message._read_ev.triggered:
                raise RuntimeError('Concurrent read attempt')
        except AttributeError:
            if message._read_ev is False:
                # All content has been read.
                self.succeed(b'')
                return
            elif message._read_ev is not None:
                # Unknown error occured.
                raise
            raise message.channel._reader_process.value

        self.all = all
        message._read_ev.succeed(self)


class Write(Event):
    def __init__(self, message, data=b'', all=False):
        Event.__init__(self, message.env)

        try:
            if message._write_ev.triggered:
                raise RuntimeError('Concurrent write attempt')
        except AttributeError:
            if message._write_ev is False:
                raise RuntimeError('Message has already been sent')
            elif message._write_ev is not None:
                # Unknown error occured.
                raise
            raise message.channel._writer_process.value

        self.data = data
        self.all = all if data else True
        message._write_ev.succeed(self)


count = 0

class Message(object):
    """Base class for parsing HTTP messages."""

    def __init__(self, sock, in_message_type, out_message_type,
            excess_data=b'', blocksize=4096):
        global count
        self.no = count
        count += 1
        self.sock = sock
        self.env = sock.env
        self.in_message_type = in_message_type
        self.out_message_type = out_message_type
        self.blocksize = blocksize
        self.max_header_size = self.blocksize

        self._recv_queue = deque()
        self._send_queue = deque()

        self._in_request_id = 0
        self._out_request_id = 0

        self._in_message_ev = None
        self._out_message_ev = None

        self._reader_process = self.env.process(self._reader(excess_data))
        self._writer_process = self.env.process(self._writer())

    def decommission(self):
        self._reader_process.interrupt()
        # TODO Let the writer finish pending writes.
        # TODO Return the _reader_process to wait upon.
        return self.excess_data

    def _reader(self, data):
        try:
            blocksize = self.blocksize

            while True:
                event = None
                message = None

                if not self._recv_queue:
                    self._in_message_ev = self.env.event()
                    yield self._in_message_ev

                message = self._recv_queue.popleft()

                # Read request header.
                idx = 0
                while True:
                    idx = data.find(b'\r\n\r\n', idx)
                    if idx >= 0: break
                    if len(data) >= self.max_header_size:
                        raise HTTPException('Header size limit exceeded')
                    idx = max(len(data) - 4, 0)
                    data += yield self.sock.read(blocksize)

                # Parse headers.
                header_data, data = data[:idx], data[idx+4:]
                message.parse_header(header_data)

                # FIXME This is ugly... Use an interrupt for this?
                self.excess_data = data

                message.succeed(message)
                self._in_request_id += 1

                # Determine the message length. From:
                # http://www.w3.org/Protocols/rfc2616/rfc2616-sec4.html#sec4
                # 1. 0 if response "MUST NOT" include a message-body (e.g. all
                #    HEAD responses, 1xx status codes, ...).
                # 2. If transfer-encoding is specified in the headers, chunked
                #    transfer coding is used determine the transfer length.
                # 3. If a content-length header field is present.
                # 4. multipart/byteranges headers also influence the transfer
                #    length, but will be ignored.

                if 'Transfer-Encoding' in message.headers:
                    chunk_size = 0
                    while chunk_size is not None:
                        event = yield message._read_ev
                        message._read_ev = self.env.event()

                        chunk = b''
                        while True:
                            # Read chunk size.
                            while True:
                                idx = data.find(b'\r\n', 1)
                                if idx >= 0: break
                                if len(data) >= self.max_header_size:
                                    raise HTTPException(
                                            'Chunk header size limit exceeded')
                                data += yield self.sock.read(self.blocksize)

                            try:
                                chunk_size = int(data[:idx], 16)
                            except:
                                raise HTTPException(
                                        'Malformed chunk header:\n%s' %
                                        data[:idx].decode('utf-8', 'replace'))

                            data = data[idx+2:]
                            if chunk_size == 0:
                                # The whole message has been read.
                                chunk_size = None
                                break

                            while len(data) < chunk_size + 2:
                                data += yield self.sock.read(self.blocksize)

                            chunk += data[:chunk_size]
                            # Strip the \r\n marker
                            data = data[chunk_size + 2:]

                            if not event.all: break

                        event.succeed(chunk)

                    # Read trailer.
                    idx = 0
                    while True:
                        idx = data.find(b'\r\n', idx)
                        if idx >= 0: break
                        if len(data) >= self.max_header_size:
                            raise HTTPException('Chunk trailer size limit '
                                    'exceeded')
                        idx = max(len(data) - 2, 0)
                        data += yield self.sock.read(blocksize)

                    # Discard trailer.
                    data = data[idx+2:]

                    message._read_ev = False
                elif 'Content-Length' in message.headers:
                    # Read up to content-length bytes.
                    try:
                        chunk_size = int(message.headers['Content-Length'])
                    except:
                        raise HTTPException('Malformed content length:\n%s' %
                                message.headers['Content-Length'])
                    event = yield message._read_ev

                    while len(data) < chunk_size:
                        data += yield self.sock.read(blocksize)

                    # Strip the \r\n marker from data
                    chunk, data = data[:chunk_size], data[chunk_size:]

                    event.succeed(chunk)
                    message._read_ev = False
                else:
                    message._read_ev = self.env.event()
                    event = yield message._read_ev
                    event.succeed(b'')
                    message._read_ev = False
        except Interrupt as i:
            # FIXME Set excess_data here?
            pass
        except GeneratorExit as e:
            pass
        except BaseException as e:
            self._reader_process.defused = True

            # Stop the writer process.
            if self._out_message_ev and not self._out_message_ev.triggered:
                self._out_message_ev.fail(e)
                self._out_message_ev = None

            if message is not None:
                if event is not None and not event.triggered:
                    event.fail(e)
                message._read_ev = None

                if not message.triggered:
                    message.fail(e)

            for message in self._recv_queue:
                message.fail(e)
            self._recv_queue = None
            raise

    def _writer(self):
        try:
            while True:
                message = None

                if not self._send_queue:
                    self._out_message_ev = self.env.event()
                    yield self._out_message_ev

                message = self._send_queue.popleft()
                # TODO Headers and statusline should already be converted to
                # iso-8859-1 in the request __init__.
                message.headers['Connection'] = 'Keep-Alive'
                headers = '\r\n'.join(
                        ['%s: %s' % item for item in message.headers.items()])
                chunk = (message.statusline + '\r\n' + headers +
                        '\r\n\r\n').encode('iso-8859-1')

                # Transmit header.
                while chunk:
                    sent = yield self.sock.write(chunk)
                    chunk = chunk[sent:]

                # Succeed message and increase request id counter.
                message.succeed(message)
                self._out_request_id += 1

                if 'Transfer-Encoding' in message.headers:
                    while True:
                        event = yield message._write_ev
                        message._write_ev = self.env.event()

                        data = event.data
                        if data:
                            chunk = (('%x\r\n' % len(data)).encode(
                                        'iso-8859-1') + data + b'\r\n')
                        else:
                            chunk = b''

                        if event.all:
                            chunk += b'0\r\n\r\n'

                        while chunk:
                            sent = yield self.sock.write(chunk)
                            chunk = chunk[sent:]

                        event.succeed()

                        if event.all:
                            break
                    message._write_ev = False
                else:
                    event = yield message._write_ev
                    chunk = event.data
                    while chunk:
                        sent = yield self.sock.write(chunk)
                        chunk = chunk[sent:]
                    event.succeed()
                    message._write_ev = False
        except GeneratorExit as e:
            pass
        except BaseException as e:
            self._writer_process.defused = True

            # Stop the reader process.
            if self._in_message_ev and not self._in_message_ev.triggered:
                self._in_message_ev.fail(e)
                self._in_message_ev = None

            if message is not None:
                if event is not None and not event.triggered:
                    event.fail(e)
                message._write_ev = None

                if not message.triggered:
                    message.fail(e)

            for message in self._send_queue:
                message.fail(e)

            self._send_queue = None
            raise

    def close(self):
        # Stop reader and writer process if they are waiting for the next
        # request.
        if self._in_message_ev and not self._in_message_ev.triggered:
            self._in_message_ev.fail(socket_error(errno.EBADF))
            self._in_message_ev = None
        if self._out_message_ev and not self._out_message_ev.triggered:
            self._out_message_ev.fail(socket_error(errno.EBADF))
            self._out_message_ev = None

        self.sock.close()


class InRequest(InMessage):
    def __init__(self, channel):
        # Check for concurrent receives.
        if channel._recv_queue:
            raise RuntimeError('Already receiving')

        InMessage.__init__(self, channel)

        self.respond = types.MethodType(OutResponse, self)
        self.response = self.env.event
        self.id = channel._in_request_id

    def parse_startline(self, startline):
        self.method, self.uri, self.version = startline.split(' ', 2)
        # TODO Split uri into path + query
        self.path = self.uri
        self.query = None


class InResponse(InMessage):
    def parse_startline(self, startline):
        self.version, self.code, self.phrase = startline.split(' ', 2)


class OutResponse(OutMessage):
    def __init__(self, request, code, phrase='', headers=None, data=None):
        # Ensure that responses are send in the same order as the requests were
        # received.
        if request.channel._out_request_id != request.id:
            raise RuntimeError('Out of order response')

        self.code = code
        self.phrase = phrase

        OutMessage.__init__(self, request.channel,
                'HTTP/1.1 %d %s' % (code, phrase), headers, data)



class OutRequest(OutMessage):
    def __init__(self, channel, method, uri, headers=None, data=None):
        # Check for concurrent requests.
        if channel._send_queue:
            raise RuntimeError('Already sending')

        OutMessage.__init__(self, channel, '%s %s HTTP/1.1' % (method, uri),
                headers, data)
        self.method = method
        self.uri = uri
        self.response = types.MethodType(InResponse, channel)


class Service(Message):
    def __init__(self, sock, excess_data=b'', blocksize=4096):
        Message.__init__(self, sock, InRequest, OutResponse, excess_data,
                blocksize)

    def recv(self):
        """Receives a message."""
        return InRequest(self)


class Client(Message):
    def __init__(self, sock, excess_data=b'', blocksize=4096):
        Message.__init__(self, sock, InResponse, OutRequest, excess_data,
                blocksize)

        self.send = types.MethodType(OutRequest, self)

    def send(self, statusline, headers=None, data=None):
        """Sends a message. Supplying ``None`` as ``data`` means to use chunked
        transfer encoding."""

        msg = OutRequest(self)
        self.incoming.append(msg)
        self.outgoing.append(msg)

        if self._out_message_wait:
            self._out_message_wait.succeed()
            self._out_message_wait = None

        return msg

    def get(self, path='', headers=None):
        return OutRequest(self, 'GET', path, headers, b'')

    def put(self, path='', headers=None, data=None):
        return OutRequest(self, 'GET', path, headers, data)


class RPCRequest(object):
    def __init__(self, connection, message):
        self.connection = connection
        self.message = message
        self.headers = {}

    def succeed(self, value):
        # Read content if it hasn't been done by the call.
        # Defuse the read attempt as failures will be handled in handler().
        # FIXME Determine somehow if the message has been read.
        self.message.read(all=True).defused = True
        self.message.respond(200, 'OK', headers=self.headers,
                data=value.encode())

    def fail(self, exc):
        # Read content if it hasn't been done by the call.
        # Defuse the read attempt as failures will be handled in handler().
        # FIXME Determine somehow if the message has been read.
        self.message.read(all=True).defused = True
        self.message.respond(404, data=b'')


class HTTP(RPC):
    def __init__(self, socket, router, client=True):
        # FIXME Do not use a flag but two classes instead.
        RPC.__init__(self, socket, router)

        if not client:
            self.channel = Service(self.socket)

    def handler(self):
        # TODO Decide if errors should be handled here, in dispatch() or in
        # callbacks to this process.
        try:
            while True:
                request = RPCRequest(self, (yield self.channel.recv()))

                # FIXME Use / lead paths again.
                path = request.message.path[1:]
                # TODO Parse query.
                args, kwargs = (), {}

                try:
                    func, obj = self.router.dispatch(self, request, path)
                except Exception as e:
                    # FIXME Shouldn't the dispatcher handle these errors?
                    request.fail(e)
                    continue

                # Check for headers.
                if hasattr(func.target, 'headers'):
                    request.headers = func.target.headers

                func(self, request, obj, args, kwargs)
        except Exception as e:
            # TODO Add proper handling of socket errors.
            pass

    class Descriptor(RPC.Descriptor):
        def headers(self, headers):
            def decorator(func):
                func.headers = headers
                return func

            return decorator
