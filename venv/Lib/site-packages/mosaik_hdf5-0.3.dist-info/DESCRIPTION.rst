mosaik-hdf5
===========

Store mosaik simulation data in an HDF5 database.

Mosaik-hdf5 stores the relations-graph of your simulation, timeseries for
entities connected to it and optionally static entity and simulation meta data.
The database structure usually looks like this::

   / [meta data]
   |
   +- Relations
   |  |
   |  +- Sim-0.Entity-1
   |  |
   |  +- PyPower-0.1-Node-2
   |
   +- Series
      |
      +- Sim-0.Entiy-1 [static data]
      |  |
      |  +- val_out
      |
      +- PyPower-0.1-Node-2 [static data]
         |
         +- P
         |
         +- Q

The *Relations* group contains one dataset for every entity. For each of the
entity's relations, the dataset has one tuple *(path_to_relation,
path_to_relatio_series)*.

The *Series* group contains (by default) one group for every entity. Each of
these group as one dataset for every attribute.

Static entity data is stored as attributes in the entity groups. Simulation
meta data is stored as attributes of the root group.

You can, optionally, create a more nested structure for the series, for
example, if you want to group entities by simulator and/or simulator instance.
This is done via regular expression replacements based on the entity ID.


Installation
------------

*mosaik-hdf5* uses the `h5py`__ module. If you get an error during installation
that `hdf5.h` is missing, install the HDF5 headers (e.g., ``sudo apt-get
install libhdf5-dev`` or ``brew install hdf5``) or use a binary package (e.g.,
for `Windows`__)

::

    $ pip install mosaik-hdf5

__ http://www.h5py.org/
__ http://www.lfd.uci.edu/~gohlke/pythonlibs/#h5py


Usage
-----

You can run mosaik-hdf5 as a sub-process or your simulation or in-process with
it. Here are example configurations for both variants:

.. code-block:: python

   sim_config = {
       'HDF5-inproc': {
           'python': 'mosaik_hdf5:MosaikHdf5',
       },
       'HDF5-subproc': {
           'cmd': 'mosaik-hdf5 %(addr)s',
       },
   }

Initialization
^^^^^^^^^^^^^^

When you start mosaik-hdf5, you have to provide a *step_size* and a *duration*
argument. The *step_size* defines how often data will be collected. The
*duration* is the simulation end time in seconds. It is used to calculate the
dataset size for every time series. For example, if *duration* is half-an-hour
(1800s) and *step_size* is 60, each dataset will have a length of 30.

You can optionally pass a *series_path* tuple which contains a regular
expression pattern and replacement string (see the `Python docs`__ for
details).

For example, by default the entity IDs ``Sim-0.Entity-1`` and
``PyPower-0.1-Node-2`` would map to the series paths ``/Series/Sim-0.Entity-1``
and ``/Series/PyPower-0.1-Node-2``. But you want to group the entities by
simulator type and simulator instance. Also, since one `mosaik-pypower`__
instance can contain multiple grids, you also want to take care of that. So
what you want is something like that: ``/Series/Sim/Sim-0/Sim-0.Entity-1`` and
``/Series/PyPower/PyPower-0.1/PyPower-0.1-Node-2``. In this (rather complex)
case, *series_path* can be ``(r'(((\w+)-(\d+.\d+|\d+))[.-](.*))',
r'\3/\2/\1')``. Easy, isn't it?

__ https://docs.python.org/3/library/re.html#re.sub
__ https://pypi.python.org/pypi/mosaik-pypower

Here are two examples for this:

.. code-block:: python

   a = world.start('HDF5', step_size=60, duration=1800)

   pattern = r'(((\w+)-(\d+.\d+|\d+))[.-](.*))'
   repl = r'\3/\2/\1'
   b = world.start('HDF5', step_size=1, duration=10,
                   series_path=(pattern, repl))


Model instantiation
^^^^^^^^^^^^^^^^^^^

Every instance of mosaik-hdf5 allows you to create exactly one instance of its
*Database* model (which is also the only model provided). The *Database* has
the following parameters:

- *gridfile* is the filename of the HDF5 database that will be created.

- *buf_size* (default: 1000) is the size of the internal data buffer for each
  series dataset. Mosaik-hdf5 buffers the data for every dataset and only
  writes larger chunks of data to the disk in order to improve the writing
  performance. If you have a lot of entities (> 100k) and only little memory,
  you may reduce this number. If you have lots of RAM, you can play with larger
  buffer sizes and see if it improves the performance for you.

- *dataset_opts* (default: None) is a dictionary of arguments that get passed
  to h5py's `create_dataset()`__ method.

  This can, for example, be used to `enable compression`__ (note, that the
  *lzf* compression is not supported by all HDF5 viewers).

__ http://docs.h5py.org/en/2.3/high/dataset.html
__ http://docs.h5py.org/en/2.3/high/dataset.html#lossless-compression-filters

Examples:

.. code-block:: python

   # Basic usage
   hdf5 = world.start('HDF5', step_size=1, duration=1)
   db = hdf5.Database('data.hdf5')

   # Use gzip compression
   hdf5 = world.start('HDF5', step_size=1, duration=1)
   db = hdf5.Database('data.hdf5', dataset_opts={
       'compression': 'gzip',
       'compression_opts': 9,
   })

   # Use lzf compression and a larger buffer
   hdf5 = world.start('HDF5', step_size=1, duration=1)
   db = hdf5.Database('data.hdf5', buf_size=1336,
                      dataset_opts={'compression': 'lzf'})


Storing data
^^^^^^^^^^^^

The *Database* model has no attributes, but it accepts any inputs. This means
that you can just connect *anything* to it. For each entity and attribute that
is connected to the database, a corresponding dataset will be created in the
database.

Mosaik-hdf5 also provides to extra methods that allow you to store some
simulation meta data and static entity data. You can only use these methods
once you created an instance of the *Database* model. The method
``set_meta_data()`` takes a single dict with an arbitrary amount of key-values
pairs. The method ``set_static_data()`` takes a dict of entities and data
dicts.

In the following example, we'll create some (fake) PV entities and a power grid
(with nodes and lines). We want to store the PV's active and reactive power
*(P, Q)*, the node voltage and angle *(Vm, Va)* for all nodes and the
complex current *(I_real, I_imag)* of all branches:

.. code-block:: python

   pv_pmax = 10
   pvs = make_pvs(pv_pmax, ...)  # A list of PV entities
   nodes, lines = make_grid(...)  # Lists of nodes/lines of a power grid

   hdf5 = world.start('HDF5', step_size=1, duration=10)
   db = hdf5.Database('data.hdf5')

   # Store meta and static data
   hdf5.set_meta_data({'duration': 10, 'description': 'hdf5 demo'}
   hdf5.set_static_data({pv.full_id: {'p_max': pv_pmax} for pv in pvs})

   # Connect inputs to database
   mosaik.util.connect_many_to_one(world, pvs, db, 'P', 'Q')
   mosaik.util.connect_many_to_one(world, nodes, db, 'Vm', 'Va')
   mosaik.util.connect_many_to_one(world, lines, db, 'I_real', 'I_imag')

For a real example, you can take a look at the `mosaik-demo`__.

__ https://bitbucket.org/mosaik/mosaik-demo/src/tip/demo.py


Getting help
------------

If you need, please visit the `mosaik-users mailing list`__ .

__ https://mosaik.offis.de/mailinglist


Changelog
=========

0.3 - 2016-02-15
----------------

- [NEW] Implemented the new "setup_done()" method.


0.2 – 2014-10-29
----------------

- [NEW] More documentation
- [NEW] Static and simulation meta data can now be stored (`issue #1`_).
- [NEW] Datasets can now be stored in arbitrarily defined paths (using complex
  regular expression replacements based on the entity ID) (`issue #4`_).

.. _`issue #1`: https://bitbucket.org/mosaik/mosaik-hdf5/issue/1/
.. _`issue #4`: https://bitbucket.org/mosaik/mosaik-hdf5/issue/4/


0.1.2 – 2014-09-22
------------------

- [CHANGE] Updated to mosaik-api 2.0.


0.1.1 – 2014-07-31
------------------

- [FIX] Fixed a regression in 0.1.


0.1 – 2014-07-31
----------------

- Initial release


Authors
=======

The mosaik HDF5 storage backend was created by Stefan Scherfke.


