"""
A PyNN version of the network architecture described in:
Muller, E., Meier, K., & Schemmel, J. (2004). Methods for simulating
high-conductance states in neural microcircuits. Proc. of BICS2004. 

http://neuralensemble.org/people/eilifmuller/Publications/bics2004_mueller.pdf

Script written by Lucas Sinclair & Eilif Muller.
LCN, EPFL - October 2009
"""

## Debugger ##
#import pdb
# pdb.set_trace()

## Import modules ##
import numpy, pylab, math, time, os, re
#import pyNN.nest as sim
from mpi4py import MPI
import pyNN.neuron as sim
import pyNN.common as common
import pyNN.connectors as connectors
import pyNN.space as space
from pyNN.utility import init_logging
from pyNN import standardmodels
#import nest
import logging



###################### CLASSES ###########################
class LatticeConnector(connectors.Connector):
    """
    Each post-synaptic neuron is connected to exactly n pre-synaptic neurons
    chosen at random.

    For every connection that is made the delay is set proportional to
    the distance that separates the two neurons plus some random noise
    coming from a gamma distribution.
    
    N cannot be drawn from a random distribution.
    
    Self connections are always enabled.
    """
    
    def __init__(self, weights=0.0, dist_factor=1.0, noise_factor=0.01, n=1.0):
        """
        Create a new connector.
        
        `weights`      -- The weights of all the connections made.
        `dist_factor`  -- A factor to control the delay (conversion of
                          distance to milliseconds of delay).
        `noise_factor` -- A factor to control the noise (scale of gamma 
                          distribution).
        `n`            -- Number of connections to make for each neuron.
        """
        connectors.Connector.__init__(self, weights, dist_factor*1.0)
        self.dist_factor = dist_factor
        self.noise_factor = noise_factor
        self.n = n
        
    def connect(self, projection):
        """Connect-up a Projection."""
        # Timers
        global rank
        timer0 = 0.0
        timer1 = 0.0
        timer2 = 0.0
        timer3 = 0.0
        timer4 = 0.0
        
        # Recuperate variables #
        n = self.n
        dist_factor = self.dist_factor
        noise_factor = self.noise_factor
        
        # Do some checking #
        assert dist_factor >= 0
        assert noise_factor >= 0
        if isinstance(n, int):
            assert n >= 0
        else:
            raise Exception("n must be an integer.")
        
        # Get posts and pres #
        listPostIDs = projection.post.local_cells
        listPreIDs = projection.pre.all_cells
        countPost = len(listPostIDs)
        countPre = len(listPreIDs)        
        listPreIndexes = numpy.arange(countPre)
        listPostIndexes = map(projection.post.id_to_index, listPostIDs)

        # Prepare all distances #
        allDistances = self.space.distances(projection.post.positions,projection.pre.positions)            
        
        # Get weights #
        weights = numpy.empty(n)
        weights[:] = self.weights
        is_conductance = common.is_conductance(projection.post[listPostIndexes[0]])
        weights = common.check_weight(weights, projection.synapse_type, is_conductance)

        numpy.random.seed(12345)
        
        for i in xrange(len(listPostIDs)):
            currentPostIndex = listPostIndexes[i]
            currentPostID = listPostIDs[i]
            #currentPostIDAsList = [currentPostID]
            
            # Pick n neurons at random in pre population
            myTimer = time.time()
            chosenPresIndexes = list(numpy.random.permutation(numpy.arange(countPre))[0:n])
            chosenPresIDs = list(projection.pre[chosenPresIndexes].all_cells)
            #if rank==0:
            #    print chosenPresIDs
            #chosenPresIDs = chosenPresIDs.tolist()
            timer0 += time.time() - myTimer
            
            # Get distances
            myTimer = time.time()
            #distances = allDistances[currentPostIndex,chosenPresIndexes]
            distances = allDistances[currentPostIndex,chosenPresIndexes]
            timer1 += time.time() - myTimer
                        
            # Generate gamme noise
            noise = numpy.random.gamma(1.0, noise_factor, n)
                
            # Create delays with distance and noise
            myTimer = time.time()
            delays = dist_factor * distances * (1.0+noise)
            timer2 += time.time() - myTimer
            #delays[:] = 1.0
                        
            # Check for small and big delays
            myTimer = time.time()
            delaysClipped = numpy.clip(delays,sim.get_min_delay(),sim.get_max_delay())
            howManyClipped = len((delays != delaysClipped).nonzero()[0])
            if (howManyClipped > 1):
                print "Warning: %d of %d delays were cliped because they were either bigger than the max delay or lower than the min delay." % (howManyClipped, n)
            delaysClipped = delaysClipped.tolist()
            timer3 += time.time() - myTimer
                
            # Connect everything up
            yTimer = time.time()
            projection._convergent_connect(chosenPresIDs, currentPostID, weights, delaysClipped)
            timer4 += time.time() - myTimer
            
        
        # Print timings
        if rank==0:
            print "\033[2;46m" + ("Timer 0: %5.4f seconds" % timer0).ljust(60) + "\033[m"
            print "\033[2;46m" + ("Timer 1: %5.4f seconds" % timer1).ljust(60) + "\033[m"
            print "\033[2;46m" + ("Timer 2: %5.4f seconds" % timer2).ljust(60) + "\033[m"
            print "\033[2;46m" + ("Timer 3: %5.4f seconds" % timer3).ljust(60) + "\033[m"
            print "\033[2;46m" + ("Timer 4: %5.4f seconds" % timer4).ljust(60) + "\033[m"



###################### FUNCTIONS ###########################
def printTimer(message):
    global currentTimer, rank
    if rank==0:
        string1 = "\033[0;46m" + (message + ": ").ljust(30) + "\033[m"
        string2 = "\033[1;46m" + ("%5.2f" % (time.time() - currentTimer) + " seconds").rjust(30) + "\033[m"
        print string1+string2
        currentTimer = time.time()

def printMessage(message):
    global rank
    if rank==0:
        print "\033[2;46m" + (message).ljust(60) + "\033[m"


###################### MAIN BODY ###########################
## Rank for MPI ##
global numberOfNodes, rank
numberOfNodes = sim.num_processes()
rank = sim.rank()

# Log to stderr, only warnings, errors, critical
init_logging('sim.log',num_processes=numberOfNodes,rank=rank,level=logging.DEBUG)

## Start message ##
if rank==0:
    print "\033[1;45m" + (("Lattice Simulation").rjust(38)).ljust(60) + "\033[m"
    print "\033[0;44m" + ("MPI_Rank: %d  " % rank + " MPI_Size: %d " % numberOfNodes).ljust(60) + "\033[m"


## Timer ##
global currentTimer, totalTimer
currentTimer = time.time()
totalTimer = time.time()

## Default global parameters ##
dt = 0.1 # simulation time step in milliseconds
tinit = 500.0 # simtime over which the network is allowed to settle down
tsim = 2000.0 # total simulation length in milliseconds
globalWeight = 0.002 # Weights of all connection in uS
latticeSize = 8 # number of neurons on one side of the cube
propOfI = 0.2 # proportion of neurons that are inhibitory

## Connections ##
# Rate of bkgnd #
rateE_E = 6.0 # firing rate of ghost excitatory to E neurons
rateE_I = 6.0 # firing rate of ghost excitatory to I neurons
rateI_E = 10.0 # firing rate of ghost inhibitory to E neurons
rateI_I = 10.0 # firing rate of ghost inhibitory to I neurons
# Total number of connections (constant) #
connectionsE_E = 1000.0 # number of E connections every E neuron recieves
connectionsE_I = 1000.0 # number of E connections every I neuron recieves
connectionsI_E = 250.0 # number of I connections every E neuron recieves
connectionsI_I = 250.0 # number of I connections every E neuron recieves
# Proportion of connections coming from inside #
ICFactorE_E = 0.12 # proportion of E connections every E neuron recieves that will be converted
ICFactorE_I = 0.2 # proportion of E connections every I neuron recieves that will be converted
ICFactorI_E = 0.2 # proportion of I connections every E neuron recieves that will be converted
ICFactorI_I = 0.2 # proportion of I connections every E neuron recieves that will be converted

## Change connections ##
# Number of new connections to make #
NumOfConE_E = int(connectionsE_E * ICFactorE_E)
NumOfConE_I = int(connectionsE_I * ICFactorE_I)
NumOfConI_E = int(connectionsI_E * ICFactorI_E)
NumOfConI_I = int(connectionsI_I * ICFactorI_I)

# Print out chosen values
if rank==0:
    print "\033[0;44m" + ("E_E:%5.2f  " % ICFactorE_E + " E_I:%5.2f  " % ICFactorE_I + " I_E:%5.2f  " % ICFactorI_E + " I_I:%5.2f" % ICFactorI_I).ljust(60) + "\033[m"

# The max distance is 15 approx
printMessage("Now strating lattice simulation setup.")
distanceFactor = 0.25 # How does distance convert to milliseconds of delay ?
noiseFactor = 0.2 # How much do axons tend to wonder ?

## Load standard parameter file (2 neurons) ##
# url_distant = "https://neuralensemble.org/svn/NeuroTools/trunk/std_params/"
# param_file = "PyNN/IF_cond_exp_gsfa_grr/muller_etal2007.param"
# internetPath = url_distant+param_file
localPath = "./standard_neurons.yaml"
import NeuroTools.parameters
params = NeuroTools.parameters.ParameterSet(localPath)

## Effectively zero the refractory period ##
params.excitatory.tau_refrac = dt
params.inhibitory.tau_refrac = dt

## Chose the neuron type ##
# Works only in NEST and NEURON
# Warning: don't try to use sim.cells.IF_cond_exp_gsfa_grr
myModel = sim.IF_cond_exp_gsfa_grr

## Simulation creation ##
# Creates a file that never closes
sim.setup(timestep=dt, min_delay=dt, max_delay=30.0, default_maxstep=distanceFactor, debug=True, quit_on_end=False)

## Define popultation ##
myLabelE = "Simulated excitatory adapting neurons"
myLabelI = "Simulated inhibitory adapting neurons"
numberOfNeuronsI = int(latticeSize**3 * propOfI)
numberOfNeuronsE = int(latticeSize**3 - numberOfNeuronsI)
popE = sim.Population((numberOfNeuronsE,),myModel,params.excitatory,label=myLabelE)
popI = sim.Population((numberOfNeuronsI,),myModel,params.inhibitory,label=myLabelI)
#all_cells = Assembly("All cells", popE, popI)

# excitatory Poisson
poissonE_Eparams = {'rate': rateE_E*connectionsE_E, 'start': 0.0,
                    'duration': tsim}
poissonE_Iparams = {'rate': rateE_I*connectionsE_I, 'start': 0.0,
                    'duration': tsim}

poissonE_E = sim.Population((numberOfNeuronsE,),cellclass=sim.SpikeSourcePoisson,cellparams=poissonE_Eparams,label='poissonE_E')
poissonE_I = sim.Population((numberOfNeuronsI,),cellclass=sim.SpikeSourcePoisson,cellparams=poissonE_Iparams,label='poissonE_I')


# inhibitory Poisson
poissonI_Eparams = {'rate': rateI_E*connectionsI_E, 'start': 0.0,
                    'duration': tsim}
poissonI_Iparams = {'rate': rateI_I*connectionsI_I, 'start': 0.0,
                    'duration': tsim}

poissonI_E = sim.Population((numberOfNeuronsE,),cellclass=sim.SpikeSourcePoisson,cellparams=poissonI_Eparams,label='poissonI_E')
poissonI_I = sim.Population((numberOfNeuronsI,),cellclass=sim.SpikeSourcePoisson,cellparams=poissonI_Iparams,label='poissonI_I')

## Set the position in space (lattice)##
numpy.random.seed(0)
latticePerm = numpy.random.permutation(latticeSize**3)
positionE = numpy.empty([3,numberOfNeuronsE])
positionI = numpy.empty([3,numberOfNeuronsI])
for x in numpy.arange(latticeSize):
        for y in numpy.arange(latticeSize):
            for z in numpy.arange(latticeSize):
                index = x * (latticeSize**2)  +  y * (latticeSize) + z
                currentNeuron = latticePerm[index]
                if currentNeuron > numberOfNeuronsE-1:
                    positionI[:,currentNeuron-numberOfNeuronsE] = (float(x), float(y), float(z))
                else:
                    positionE[:,currentNeuron] = (float(x), float(y), float(z))
popE.positions = positionE
popI.positions = positionI

## Random seeds ##
# seed which is different every time
#numpy.random.seed(int(time.time()*10+rank))
# seeds which are same every time
numpy.random.seed(rank)
from pyNN.random import NumpyRNG

# some random seeds which are different everytime
# and different for each node.
#seeds = numpy.arange(numberOfNodes) + int((time.time()*100)%2**32)
# seeds which are same every time, different for each node
seeds = numpy.arange(numberOfNodes)

# bcast, as we can't be sure each node has the same time, and therefore
# different seeds.  This way, all nodes get the list from rank=0.
seeds = MPI.COMM_WORLD.bcast(seeds)

#rng = NumpyRNG(seed=seeds[rank], parallel_safe=False, rank=rank,
#               num_processes=numberOfNodes)

#nest.SetKernelStatus({'rng_seeds': list(seeds)})

myconn = sim.OneToOneConnector(weights=globalWeight, delays=dt)

prjE_E = sim.Projection(poissonE_E, popE, method=myconn, target='excitatory')
prjE_I = sim.Projection(poissonE_I, popI, method=myconn, target='excitatory')

prjI_E = sim.Projection(poissonI_E, popE, method=myconn, target='inhibitory')
prjI_I = sim.Projection(poissonI_I, popI, method=myconn, target='inhibitory')

## Record the spikes ##
popE.record(to_file=False)
popI.record(to_file=False)
printTimer("Time for setup part")


###################### RUN PART ###########################
## Run the simulation without inter-connection ##
printMessage("Now running without inter-lattice connections.")
sim.run(int(tinit))
printTimer("Time for first half of run")



# Lower the external network "ghost" processes according to how many connections of that
# type were added.
poissonI_E.rate = rateI_E * (connectionsI_E - NumOfConI_E)
poissonI_I.rate = rateI_I * (connectionsI_I - NumOfConI_I)
poissonE_E.rate = rateE_E * (connectionsE_E - NumOfConE_E)
poissonE_I.rate = rateE_I * (connectionsE_I - NumOfConE_I)


# Prepare the connectors #
myConnectorE_E = LatticeConnector(weights=globalWeight, dist_factor=distanceFactor,
                                  noise_factor=noiseFactor, n=NumOfConE_E)
myConnectorE_I = LatticeConnector(weights=globalWeight, dist_factor=distanceFactor,
                                  noise_factor=noiseFactor, n=NumOfConE_I)
myConnectorI_E = LatticeConnector(weights=globalWeight, dist_factor=distanceFactor,
                                  noise_factor=noiseFactor, n=NumOfConI_E)
myConnectorI_I = LatticeConnector(weights=globalWeight, dist_factor=distanceFactor,
                                  noise_factor=noiseFactor, n=NumOfConI_I)
# Execute the projections #
printMessage("Now changing E_E connections for " + str(NumOfConE_E)+ " new connections")
prjLatticeE_E = sim.Projection(popE, popE, method=myConnectorE_E, target='excitatory')
printTimer("Time for E_E connections")

printMessage("Now changing E_I connections for " + str(NumOfConE_I)+ " new connections")
prjLatticeE_I = sim.Projection(popE, popI, method=myConnectorE_I, target='excitatory')
printTimer("Time for E_I connections")

printMessage("Now changing I_E connections for " + str(NumOfConI_E)+ " new connections")
prjLatticeI_E = sim.Projection(popI, popE, method=myConnectorI_E, target='inhibitory')
printTimer("Time for I_E connections")

printMessage("Now changing I_I connections for " + str(NumOfConI_I)+ " new connections")
prjLatticeI_I = sim.Projection(popI, popI, method=myConnectorI_I, target='inhibitory')
printTimer("Time for I_I connections")

## Run the simulation once lattice is inter-connected ##
printMessage("Now running with inter-lattice connections.")
sim.run(int(tsim-tinit))
printTimer("Time for second half of run")
simTimer = time.time()

###################### END PART ###########################
printMessage("Now creating graph.")
time.sleep(2)

## Get spikes ##
spikesE = popE.getSpikes()
popE.printSpikes('spikes.dat')
spikesI = popI.getSpikes()

## Process them ##
if rank==0:
    highestIndexE = numpy.max(spikesE[:,0])
    listNeuronsE = list(spikesE[:,0])
    listTimesE = list(spikesE[:,1])
    listNeuronsI = list(spikesI[:,0] + highestIndexE) 
    listTimesI = list(spikesI[:,1])

## Kill the bad dir ##
#print "Tempdir: ", sim.tempdirs
#theBadDir = sim.tempdirs
#thePipe = os.popen("lsof -F f +D " + theBadDir[0])
#theText = thePipe.read()
#sts = thePipe.close()
#m = re.search('\nf(\w+)\n', theText)
#theFD = m.group(1)
#os.close(int(theFD))
    
## Close the simulation ##
sim.end()


###################### PLOTTING ###########################
if rank==0:
    
## Graph Burst ##
    pylab.figure()
    allSpikes = listTimesE+listTimesI
    allNeurons = listNeuronsE+listNeuronsI
    pylab.plot(allSpikes,allNeurons,'r.',markersize=1,label='Action potentials')
    
    pylab.xlabel("Time [milliseconds]")
    pylab.ylabel("Neuron (first E, then I)")
    pylab.title(("$C_{E\\rightarrow E}=%.2f$, $C_{E\\rightarrow I}=%.2f$,"+\
               "$C_{I\\rightarrow E}=%.2f$, $C_{I\\rightarrow I}=%.2f$,") % \
                (ICFactorE_E, ICFactorE_I, ICFactorI_E, ICFactorI_I))
    pylab.suptitle("Layer 4 model with Connection Factors:")
    #pylab.legend()
    
    axisHeight = pylab.axis()[3]
    pylab.vlines(tinit,0.0,axisHeight/8,linewidth="4",color='k',linestyles='solid')

    #pylab.plot(tbins,axisHeight/8/numpy.max(f)*f,linewidth="2",color='b',linestyle='steps-post')

    if numberOfNodes != 0:
        pylab.savefig("myFigure.pdf")
        #os.system("display myFigure.pdf &")
        #os.popen("display myFigure.pdf &")
        #pid = os.spawnlp(os.P_NOWAIT, "display", "myFigure.pdf")


## Total times ##
    printTimer("Time for graphing results")

    string1 = "\033[0;44m" + ("Total simulation time: ").ljust(30) + "\033[m"
    string2 = "\033[1;44m" + ("%5.2f" % (simTimer - totalTimer) + " seconds").rjust(30) + "\033[m"
    print string1+string2

    string1 = "\033[0;44m" + ("Total time: ").ljust(30) + "\033[m"
    string2 = "\033[1;44m" + ("%5.2f" % (time.time() - totalTimer) + " seconds").rjust(30) + "\033[m"
    print string1+string2
