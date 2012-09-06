# encoding: utf8
"""
Implementation of the "low-level" functionality used by the common
implementation of the API, for the NEURON simulator.

Functions and classes useable by the common implementation:

Functions:
    reset()
    run()
    finalize()

Classes:
    ID
    Recorder
    Connection
    
Attributes:
    state -- a singleton instance of the _State class.
    recorder_list

All other functions and classes are private, and should not be used by other
modules.

:copyright: Copyright 2006-2011 by the PyNN team, see AUTHORS.
:license: CeCILL, see LICENSE for details.

$Id: simulator.py 1070 2012-03-08 16:42:31Z apdavison $
"""

from pyNN import __path__ as pyNN_path
from pyNN import common, errors, core
import platform
import logging
import numpy
import os.path
from neuron import h, load_mechanisms

# Global variables
nrn_dll_loaded = []
recorder_list = []
gid_sources = []
logger = logging.getLogger("PyNN")

# --- Internal NEURON functionality -------------------------------------------- 

def is_point_process(obj):
    """Determine whether a particular object is a NEURON point process."""
    return hasattr(obj, 'loc')

def register_gid(gid, source, section=None):
    """Register a global ID with the global `ParallelContext` instance."""
    ###print "registering gid %s to %s (section=%s)" % (gid, source, section)
    state.parallel_context.set_gid2node(gid, state.mpi_rank) # assign the gid to this node
    if is_point_process(source):
        nc = h.NetCon(source, None)                          # } associate the cell spike source
    else:
        nc = h.NetCon(source, None, sec=section)
    state.parallel_context.cell(gid, nc)              # } with the gid (using a temporary NetCon)
    gid_sources.append(source) # gid_clear (in _State.reset()) will cause a
                               # segmentation fault if any of the sources
                               # registered using pc.cell() no longer exist, so
                               # we keep a reference to all sources in the
                               # global gid_sources list. It would be nicer to
                               # be able to unregister a gid and have a __del__
                               # method in ID, but this will do for now.

def nativeRNG_pick(n, rng, distribution='uniform', parameters=[0,1]):
    """
    Pick random numbers from a Hoc Random object.
    
    Return a Numpy array.
    """
    native_rng = h.Random(0 or rng.seed)
    rarr = [getattr(native_rng, distribution)(*parameters)]
    rarr.extend([native_rng.repick() for j in xrange(n-1)])
    return numpy.array(rarr)

def h_property(name):
    """Return a property that accesses a global variable in Hoc."""
    def _get(self):
        return getattr(h, name)
    def _set(self, val):
        setattr(h, name, val)
    return property(fget=_get, fset=_set)

class _Initializer(object):
    """
    Manage initialization of NEURON cells. Rather than create an
    `FInializeHandler` instance for each cell that needs to initialize itself,
    we create a single instance, and use an instance of this class to maintain
    a list of cells that need to be initialized.
    
    Public methods:
        register()
    """
    
    def __init__(self):
        """
        Create an `FinitializeHandler` object in Hoc, which will call the
        `_initialize()` method when NEURON is initialized.
        """
        h('objref initializer')
        h.initializer = self
        self.fih = h.FInitializeHandler(1, "initializer._initialize()")
        self.clear()
    
    def register(self, *items):
        """
        Add items to the list of cells/populations to be initialized. Cell
        objects must have a `memb_init()` method.
        """
        for item in items:
            if isinstance(item, (common.BasePopulation, common.Assembly)):
                if "Source" not in item.celltype.__class__.__name__: # don't do memb_init() on spike sources
                    self.population_list.append(item)
            else:
                if hasattr(item._cell, "memb_init"):
                    self.cell_list.append(item)
    
    def _initialize(self):
        """Call `memb_init()` for all registered cell objects."""
        logger.info("Initializing membrane potential of %d cells and %d Populations." % \
                     (len(self.cell_list), len(self.population_list)))
        for cell in self.cell_list:
            cell._cell.memb_init()
        for population in self.population_list:
            for cell in population:
                cell._cell.memb_init()

    def clear(self):
        self.cell_list = []
        self.population_list = []
        

# --- For implementation of get_time_step() and similar functions --------------

class _State(object):
    """Represent the simulator state."""
    
    def __init__(self):
        """Initialize the simulator."""
        h('min_delay = 0')
        h('tstop = 0')
        h('steps_per_ms = 1/dt')
        self.parallel_context = h.ParallelContext()
        self.parallel_context.spike_compress(1, 0)
        self.num_processes = int(self.parallel_context.nhost())
        self.mpi_rank = int(self.parallel_context.id())
        self.cvode = h.CVode()
        h('objref plastic_connections')
        self.clear()
        self.default_maxstep=10.0
    
    t = h_property('t')
    def __get_dt(self):
        return h.dt
    def __set_dt(self, dt):
        h.steps_per_ms = 1.0/dt
        h.dt = dt
    dt = property(fget=__get_dt, fset=__set_dt)
    tstop = h_property('tstop')         # } these are stored in hoc so that we
    min_delay = h_property('min_delay') # } can interact with the GUI

    def clear(self):
        global gid_sources
        self.parallel_context.gid_clear()
        gid_sources = []
        self.gid_counter = 0
        self.running = False
        h.plastic_connections = []

def reset():
    """Reset the state of the current network to time t = 0."""
    state.running = False
    state.t = 0
    state.tstop = 0
    h.finitialize()

def run(simtime):
    """Advance the simulation for a certain time."""
    if not state.running:
        state.running = True
        local_minimum_delay = state.parallel_context.set_maxstep(state.default_maxstep)
        h.finitialize()
        state.tstop = 0
        logger.debug("default_maxstep on host #%d = %g" % (state.mpi_rank, state.default_maxstep ))
        logger.debug("local_minimum_delay on host #%d = %g" % (state.mpi_rank, local_minimum_delay))
        if state.num_processes > 1:
            assert local_minimum_delay >= state.min_delay, \
                   "There are connections with delays (%g) shorter than the minimum delay (%g)" % (local_minimum_delay, state.min_delay)
    state.tstop += simtime
    logger.info("Running the simulation for %g ms" % simtime)
    state.parallel_context.psolve(state.tstop)

def finalize(quit=False):
    """Finish using NEURON."""
    state.parallel_context.runworker()
    state.parallel_context.done()
    if quit:
        logger.info("Finishing up with NEURON.")
        h.quit()


# --- For implementation of access to individual neurons' parameters -----------

class ID(int, common.IDMixin):
    __doc__ = common.IDMixin.__doc__
    
    def __init__(self, n):
        """Create an ID object with numerical value `n`."""
        int.__init__(n)
        common.IDMixin.__init__(self)
    
    def _build_cell(self, cell_model, cell_parameters):
        """
        Create a cell in NEURON, and register its global ID.
        
        `cell_model` -- one of the cell classes defined in the
                        `neuron.cells` module (more generally, any class that
                        implements a certain interface, but I haven't
                        explicitly described that yet).
        `cell_parameters` -- a dictionary containing the parameters used to
                             initialise the cell model.
        """
        gid = int(self)
        self._cell = cell_model(**cell_parameters)          # create the cell object
        register_gid(gid, self._cell.source, section=self._cell.source_section)
        if hasattr(self._cell, "get_threshold"):            # this is not adequate, since the threshold may be changed after cell creation
            state.parallel_context.threshold(int(self), self._cell.get_threshold()) # the problem is that self._cell does not know its own gid
        
    def get_native_parameters(self):
        """Return a dictionary of parameters for the NEURON cell model."""
        D = {}
        for name in self._cell.parameter_names:
            D[name] = getattr(self._cell, name)
        return D
    
    def set_native_parameters(self, parameters):
        """Set parameters of the NEURON cell model from a dictionary."""
        for name, val in parameters.items():
            setattr(self._cell, name, val)
        
    def get_initial_value(self, variable):
        """Get the initial value of a state variable of the cell."""
        return getattr(self._cell, "%s_init" % variable)
        
    def set_initial_value(self, variable, value):
        """Set the initial value of a state variable of the cell."""
        index = self.parent.id_to_local_index(self)
        self.parent.initial_values[variable][index] = value
        setattr(self._cell, "%s_init" % variable, value)


# --- For implementation of connect() and Connector classes --------------------

class Connection(object):
    """
    Store an individual plastic connection and information about it. Provide an
    interface that allows access to the connection's weight, delay and other
    attributes.
    """

    def __init__(self, source, target, nc):
        """
        Create a new connection.
        
        `source` -- ID of pre-synaptic neuron.
        `target` -- ID of post-synaptic neuron.
        `nc` -- a Hoc NetCon object.
        """
        self.source = source
        self.target = target
        self.nc = nc
        
    def useSTDP(self, mechanism, parameters, ddf):
        """
        Set this connection to use spike-timing-dependent plasticity.
        
        `mechanism`  -- the name of an NMODL mechanism that modifies synaptic
                        weights based on the times of pre- and post-synaptic spikes.
        `parameters` -- a dictionary containing the parameters of the weight-
                        adjuster mechanism.
        `ddf`        -- dendritic delay fraction. If ddf=1, the synaptic delay
                        `d` is considered to occur entirely in the post-synaptic
                        dendrite, i.e., the weight adjuster receives the pre-
                        synaptic spike at the time of emission, and the post-
                        synaptic spike a time `d` after emission. If ddf=0, the
                        synaptic delay is considered to occur entirely in the
                        pre-synaptic axon.
        """
        self.ddf = ddf
        self.weight_adjuster = getattr(h, mechanism)(0.5)
        self.pre2wa = state.parallel_context.gid_connect(int(self.source), self.weight_adjuster)
        self.pre2wa.threshold = self.nc.threshold
        self.pre2wa.delay = self.nc.delay * (1-ddf)
        self.pre2wa.weight[0] = 1
        # directly create NetCon as wa is on the same machine as the post-synaptic cell
        self.post2wa = h.NetCon(self.target._cell.source, self.weight_adjuster,
                                sec=self.target._cell.source_section)
        self.post2wa.threshold = 1
        self.post2wa.delay = self.nc.delay * ddf
        self.post2wa.weight[0] = -1
        for name, value in parameters.items():
            setattr(self.weight_adjuster, name, value)
        # setpointer
        i = len(h.plastic_connections)
        h.plastic_connections.append(self)
        h('setpointer plastic_connections._[%d].weight_adjuster.wsyn, plastic_connections._[%d].nc.weight' % (i,i))

    def _set_weight(self, w):
        self.nc.weight[0] = w

    def _get_weight(self):
        """Synaptic weight in nA or µS."""
        return self.nc.weight[0]

    def _set_delay(self, d):
        self.nc.delay = d
        if hasattr(self, 'pre2wa'):
            self.pre2wa.delay = float(d)*(1-self.ddf)
            self.post2wa.delay = float(d)*self.ddf

    def _get_delay(self):
        """Connection delay in ms."""
        return self.nc.delay

    weight = property(_get_weight, _set_weight)
    delay = property(_get_delay, _set_delay)

def generate_synapse_property(name):
    def _get(self):
        synapse = self.nc.syn()
        if hasattr(synapse, name):
            return getattr(synapse, name)
        else:
            raise Exception("synapse type does not have an attribute '%s'" % name)
    def _set(self, val):
        synapse = self.nc.syn()
        if hasattr(synapse, name):
            setattr(synapse, name, val)
        else:
            raise Exception("synapse type does not have an attribute '%s'" % name)
    return property(_get, _set)
setattr(Connection, 'U', generate_synapse_property('U'))
setattr(Connection, 'tau_rec', generate_synapse_property('tau_rec'))
setattr(Connection, 'tau_facil', generate_synapse_property('tau_facil'))
setattr(Connection, 'u0', generate_synapse_property('u0'))

def generate_stdp_property(name):
    def _get(self):
        return getattr(self.weight_adjuster, name)
    def _set(self, val):
        setattr(self.weight_adjuster, name, val)
    return property(_get, _set)
setattr(Connection, 'w_max', generate_stdp_property('wmax'))
setattr(Connection, 'w_min', generate_stdp_property('wmin'))
setattr(Connection, 'A_plus', generate_stdp_property('aLTP'))
setattr(Connection, 'A_minus', generate_stdp_property('aLTD'))
setattr(Connection, 'tau_plus', generate_stdp_property('tauLTP'))
setattr(Connection, 'tau_minus', generate_stdp_property('tauLTD'))


# --- Initialization, and module attributes ------------------------------------

mech_path = os.path.join(pyNN_path[0], 'neuron', 'nmodl')
load_mechanisms(mech_path) # maintains a list of mechanisms that have already been imported
state = _State()  # a Singleton, so only a single instance ever exists
del _State
initializer = _Initializer()
del _Initializer
