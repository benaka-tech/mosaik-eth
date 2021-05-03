"""
Store mosaik simulation data in an HDF5 database.

"""
import json
import re

import h5py
import mosaik_api
import networkx as nx
import numpy as np


__version__ = '0.3'
meta = {
    'models': {
        'Database': {
            'public': True,
            'any_inputs': True,
            'params': ['filename', 'buf_size', 'dataset_opts'],
            'attrs': [],
        },
    },
    'extra_methods': [
        'set_meta_data',
        'set_static_data',
    ],
}


class MosaikHdf5(mosaik_api.Simulator):
    def __init__(self):
        super().__init__(meta)
        self.eid = 'hdf5db'

        # Set in init()
        self.sid = None
        self.step_size = None
        self.duration = None
        self.ds_size = None
        self.series_path = None  # regex object for the series path
        self.series_path_repl = None  # replacement string for series path

        # Set in create()
        self.db = None
        self.rels = None
        self.series = None
        self.buf_size = None
        self.dataset_opts = {}

        # Used in step()
        self.eid_path = {}  # Stores the series path for an entity
        self.data_buf = {}

    def init(self, sid, step_size, duration, series_path=(None, None)):
        self.sid = sid
        self.step_size = step_size
        self.duration = duration
        self.ds_size = self.duration // self.step_size
        if series_path[0] is not None:
            self.series_path = re.compile(series_path[0])
            self.series_path_repl = series_path[1]

        return self.meta

    def create(self, num, model, filename, buf_size=1000, dataset_opts=None):
        if num != 1 or self.db is not None:
            raise ValueError('Can only create one database.')
        if model != 'Database':
            raise ValueError('Unknown model: "%s"' % model)

        self.buf_size = buf_size
        if dataset_opts:
            self.dataset_opts.update(dataset_opts)

        self.db = h5py.File(filename, 'w')
        self.rels = self.db.create_group('Relations')
        self.series = self.db.create_group('Series')

        return [{'eid': self.eid, 'type': model, 'rel': []}]

    def setup_done(self):
        yield from self._store_relations()

    def step(self, time, inputs):
        assert len(inputs) == 1
        inputs = inputs[self.eid]

        # Store series
        g_series = self.series
        buf_size = self.buf_size
        eid_path = self.eid_path
        buf = self.data_buf
        abs_idx = time // self.step_size
        rel_idx = abs_idx % buf_size

        for attr, data in inputs.items():
            for src_id, value in data.items():
                if time == 0:
                    self._create_dataset(src_id, attr, type(value),
                                         self.ds_size, buf, buf_size)

                path = eid_path[src_id]
                key = '%s/%s' % (path, attr)

                # Buffer data to improve performance
                buf[key][rel_idx] = value

        buf_len = rel_idx + 1
        last_step = bool(time + self.step_size >= self.duration)
        if buf_len == buf_size or last_step:
            # Write and clear buffer
            start = abs_idx - rel_idx
            end = start + buf_len
            for key, val in buf.items():
                g_series[key][start:end] = buf[key][:buf_len]

        return time + self.step_size

    def set_meta_data(self, data):
        self._save_attrs(self.db, data)

    def set_static_data(self, data):
        for eid, attrs in data.items():
            g = self._get_group(eid)
            self._save_attrs(g, attrs)

    def _store_relations(self):
        """Query relations graph and store it in the database."""
        db_full_id = '%s.%s' % (self.sid, self.eid)
        data = yield self.mosaik.get_related_entities()
        nxg = nx.Graph()
        nxg.add_nodes_from(data['nodes'].items())
        nxg.add_edges_from(data['edges'])

        s_name = self.series.name
        r_name = self.rels.name
        for node, neighbors in sorted(nxg.adj.items()):
            if node == db_full_id:
                continue
            rels = sorted(n for n in neighbors if n != db_full_id)
            rels = np.array([
                (
                    ('%s/%s' % (r_name, n)).encode(),
                    ('%s/%s' % (s_name, self._get_entity_path(n))).encode(),
                ) for n in rels
            ], dtype=(bytes, bytes))
            self.rels.create_dataset(node, data=rels, **self.dataset_opts)

    def _create_dataset(self, src_id, attr, dtype, ds_size, buf, buf_size):
        """Create a dataset for the attribute *attr* of entity *src_id*.

        The dataset will use the type *dtype* and will have the size *ds_size*.

        Also initialize the buffer *buf* with size *buf_size*.

        """
        g = self._get_group(src_id)
        ds = g.create_dataset(attr, (ds_size,), dtype=np.dtype(dtype),
                              **self.dataset_opts)
        buf[ds.name] = np.empty(buf_size, dtype=dtype)

    def _get_group(self, eid):
        """Get or create group for entity *eid*."""
        try:
            path = self.eid_path[eid]
            g = self.series[path]
        except KeyError:
            path = self._get_entity_path(eid)
            g = self.series.create_group(path)
            self.eid_path[eid] = g.name

        return g

    def _get_entity_path(self, eid):
        if self.series_path is not None:
            path = self.series_path.sub(self.series_path_repl, eid)
        else:
            path = eid
        return path

    def _save_attrs(self, g, attrs):
        for k, v in attrs.items():
            print(type(v))
            # type(v) is in (int, float, str, list, dict, bool, type(None))
            if type(v) in (list, dict, tuple):
                g.attrs[k] = json.dumps(v).encode()
            else:
                g.attrs[k] = v


def main():
    desc = __doc__.strip()
    mosaik_api.start_simulation(MosaikHdf5(), desc)
