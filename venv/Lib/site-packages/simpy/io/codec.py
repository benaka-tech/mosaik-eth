from __future__ import absolute_import
from json import JSONEncoder, JSONDecoder


# TODO There should be an easier API to specify types and convertors. Maybe
# also accept an object with encode and decode functions?


class AbstractCodec(object):
    @staticmethod
    def expand_datatype_list(datatypes):
        expanded = []
        for dtype in datatypes:
            if type(dtype) is not tuple:
                try:
                    if not type(dtype) is type:
                        raise ValueError('%s is not a type' % dtype)

                    expanded.append((dtype, dtype.encode, dtype.decode))
                except Exception as e:
                    raise ValueError('Invalid datatype specification %s' %
                            datatypes)
            else:
                if not len(dtype) == 3:
                    raise ValueError('Datatype specifications must a tuple '
                            'with three elements or a type with encode and '
                            'decode functions but not %s' % dtype)

                expanded.append(dtype)

        return tuple(expanded)

    @staticmethod
    def expand_converter_list(converters):
        expanded = []
        for converter in converters:
            if type(converter) is not tuple:
                try:
                    expanded.append((converter.encode, converter.decode))
                except Exception as e:
                    raise ValueError('Invalid convertor specification %s' %
                            converters)
            else:
                if not len(converter) == 2:
                    raise ValueError('Convertor specifications must a tuple '
                            'with two elements or an object with encode and '
                            'decode functions but not %s' % converter)

                expanded.append(converter)

        return tuple(expanded)

    def encode(self, obj):
        raise NotImplementedError(self)

    def decode(self, stream):
        raise NotImplementedError(self)


class JSON(AbstractCodec):
    def __init__(self, types=(), converters=(), custom_typeid='__type__'):
        self.types = AbstractCodec.expand_datatype_list(types)
        self.converters = AbstractCodec.expand_converter_list(converters)
        self.custom_typeid = custom_typeid

        self.encoder = JSONEncoder(default=self._box_object)
        self.decoder = JSONDecoder(object_hook=self._unbox_object)

        self.encoders = dict((datatype, (idx, encode))
                for idx, (datatype, encode, decode) in enumerate(self.types))
        self.inflaters = tuple((idx + len(self.types), inflate)
                for idx, (inflate, deflate) in enumerate(self.converters))

        self.decoders = tuple(decode
                for datatype, encode, decode in self.types)
        self.decoders += tuple(deflate for inflate, deflate in self.converters)

    def _box_object(self, obj):
        try:
            typeid, encode = self.encoders[type(obj)]
            return {self.custom_typeid: (typeid, encode(obj))}
        except KeyError:
            for typeid, inflate in self.inflaters:
                result = inflate(obj)
                if result is not None:
                    break
            else:
                raise TypeError('Cannot encode objects of type %s' %
                        type(obj).__name__)

            return {self.custom_typeid: (typeid, result)}

    def _unbox_object(self, obj):
        try:
            typeid, data = obj[self.custom_typeid]
        except (KeyError, ValueError):
            return obj

        try:
            decode = self.decoders[typeid]
        except IndexError:
            raise TypeError('Invalid type identifier %s' % typeid)

        return decode(data)

    def decode(self, data):
        try:
            return self.decoder.decode(data)
        except BaseException as e:
            raise ValueError('Failed to decode "%s"' % str(data))

    def encode(self, obj):
        try:
            return self.encoder.encode(obj)
        except BaseException as e:
            raise ValueError('Failed to encode "%s"' % str(obj))
