"""
For every function, class and method found in the common module, this script
checks that the same function, etc, with the same argument names, exists in the
simulator-specific modules.

Needs to be extended to check that arguments have the same default arguments
(see http://www.faqts.com/knowledge_base/view.phtml/aid/5666 for how to obtain
default values of args).

Andrew P. Davison, CNRS, UNIC, May 2006
$Id: checkAPI.py 812 2010-11-03 15:36:29Z apdavison $
"""

import re, string, types, getopt, sys, shutil, os, inspect, math
#shutil.copy('dummy_hoc.py','hoc.py')
from pyNN import common, nest, neuron, pcsim, brian
#os.remove('hoc.py') #; os.remove('hoc.pyc')


red     = 0010; green  = 0020; yellow = 0030; blue = 0040;
magenta = 0050; cyan   = 0060; bright = 0100
try:
    import ll.ansistyle
    coloured = True
except ImportError:
    coloured = False

# Define some constants
verbose = False
indent = 32
ok = "     ok  "
notfound = "     --  "
inconsistent_args  = "     XX  "
inconsistent_doc   = "    ~ok  "
missing_doc = "    ~ok  "
inconsistency = ""

# Note that we exclude built-ins, modules imported from the standard library,
# and classes defined only in common.
exclude_list = ['__module__','__doc__','__builtins__','__file__','__class__',
                '__delattr__', '__dict__', '__getattribute__', '__hash__',
                '__new__','__reduce__','__reduce_ex__','__repr__','__setattr__',
                '__str__','__weakref__',
                'time','types','copy', 'sys', 'numpy', 'random',
                '_abstract_method', '_function_id', 'distance', 'distances',
                'build_translations',
                'InvalidParameterValueError', 'NonExistentParameterError',
                'InvalidDimensionsError', 'ConnectionError', 'RoundingWarning',
                'StandardCellType', 'Connector', 'StandardModelType',
                'STDPTimingDependence', 'STDPWeightDependence', 'ShortTermPlasticityMechanism',
                'ModelNotAvailable', 'IDMixin',
                '_tcall', '_call',
                ] + dir(math)

module_list = [nest, neuron, pcsim, brian]

if coloured:
    def colour(col,text):
        return str(ll.ansistyle.Text(col,text))
    ok = colour(bright+green,ok)
    inconsistent_args = colour(red,inconsistent_args)
    notfound = colour(yellow+bright,notfound)
    inconsistent_doc = colour(bright+magenta,inconsistent_doc)
    missing_doc = colour(green,missing_doc)
else:
    def colour(col,text):
        return text

def funcArgs(func):
    if hasattr(func,'im_func'):
        func = func.im_func
    if hasattr(func,'func_code'):
        code = func.func_code
        fname = code.co_name
        args = inspect.getargspec(func)
    else:
        args = ()
        fname = func.__name__
    try:
        func_args = "%s(%s)" % (fname, inspect.formatargspec(*args))
        return func_args
    except TypeError:
        print "Error with", func
        return "%s()" % fname

def checkDoc(str1,str2):
    """The __doc__ string for the simulator specific classes/functions/methods
    must match that for the common definition at the start. Further information
    can be added at the end."""
    global inconsistency
    if str1 and str2:
        str1 = ' '.join(str1.strip().split()) # ignore differences in white space
        str2 = ' '.join(str2.strip().split())
        nchar1 = len(str1)
        if nchar1 <= len(str2) and str2[0:nchar1] == str1:
            retstr = ok
        else:
            retstr = inconsistent_doc
            inconsistency += "    [" + str1.replace("\n","") + "]\n" + colour(magenta,"    [" + str2.replace("\n","") + "]") + "\n"
    else:
        retstr = missing_doc
        #inconsistency += colour(bright+magenta,'    [Missing]') + "\n"
    return retstr

def checkFunction(func):
    """Checks that the functions have the same names, argument names, and
    __doc__ strings."""
    str = ""
    differences = ""
    common_args = funcArgs(func)
    common_doc  = func.__doc__
    for module in module_list:
        if dir(module).__contains__(func.func_name):
            modfunc = getattr(module,func.func_name)
            module_args = funcArgs(modfunc)
            if common_args == module_args:
                module_doc = modfunc.__doc__
                str += checkDoc(common_doc,module_doc)
            else:
                str += inconsistent_args
                differences += common_args + " != " + module_args + "\n           "
        else:
            str += notfound
    return str, differences

def checkClass(classname):
    """Checks that the classes have the same method names and the same
    __doc__ strings."""
    str = ""
    common_doc  = getattr(common,classname).__doc__
    for module in module_list:            
        if dir(module).__contains__(classname):
            module_doc = getattr(module,classname).__doc__
            str += checkDoc(common_doc,module_doc)
        else:
            str += notfound
    return str

def checkMethod(meth,classname):
    """Checks that the methods have the same names, argument names, and
    __doc__ strings."""
    str = ""
    differences = ""
    common_args = funcArgs(meth.im_func)
    common_doc  = meth.im_func.__doc__
    #for cls in [getattr(m,classname) for m in module_list if hasattr(m,classname)]:
    for m in module_list:
        if hasattr(m, classname):
            cls = getattr(m,classname)
            if hasattr(cls, meth.im_func.func_name): #dir(cls).__contains__(meth.im_func.func_name):
                modulemeth = getattr(cls,meth.im_func.func_name)
                module_args = funcArgs(modulemeth)
                module_doc  = modulemeth.im_func.__doc__
                if common_args == module_args:
                    str += checkDoc(common_doc,module_doc)
                else:
                    str += inconsistent_args
                    differences += common_args + " != " + module_args + "\n           "
            else:
                str += notfound
        else:
            str += notfound
    return str, differences

def checkStaticMethod(meth,classname):
    """Checks that the methods have the same names, argument names, and
    __doc__ strings."""
    str = ""
    common_args = funcArgs(meth)
    common_doc  = meth.__doc__
    for cls in [getattr(m,classname) for m in module_list]:
        if dir(cls).__contains__(meth.func_name):
            modulemeth = getattr(cls,meth.func_name)
            module_args = funcArgs(modulemeth)
            module_doc = modulemeth.__doc__
            if common_args == module_args:
                str += checkDoc(common_doc,module_doc)
            else:
                str += inconsistent_args + common_args + "!=" + module_args
        else:
            str += notfound
    return str

def checkData(varname):
    """Checks that all modules contain data items with the same name."""
    str = ""
    for module in module_list:
        if dir(module).__contains__(varname):
            str += ok
        else:
            str += notfound
    return str

# Main script

if __name__ == "__main__":
    
    # Parse command line arguments
    verbose = False
    try:
        opts, args = getopt.getopt(sys.argv[1:],"v")
        for opt, arg in opts:
            if opt == "-v":
                verbose = True
    except getopt.GetoptError:
        print "Usage: python checkAPI.py [options]\n\nValid options: -v  : verbose output"
        sys.exit(2)

    header = "   ".join(m.__name__.replace('pyNN.','') for m in module_list)
    print "\n%s%s" % (" "*(indent+3),header)
    for item in dir(common):
        if item not in exclude_list:
            fmt = "%s-%ds " % ("%",indent)
            line = ""
            difference = ""
            fm = getattr(common,item)
            if type(fm) == types.FunctionType:
                line += colour(yellow,fmt % item) #+ '(function)    '
                result, diff = checkFunction(fm)
                line += result
                if diff: difference += " " + diff
            elif type(fm) == types.ClassType or type(fm) == types.TypeType:
                line += colour(cyan,fmt % item) #+ '(class)       '
                line += checkClass(item)
                if line: print line
                if verbose:
                    if inconsistency: print inconsistency.strip("\n")
                    inconsistency = ""
                for subitem in dir(fm):
                    if subitem not in exclude_list:
                        line = ""; difference = ""
                        fmt = "  %s-%ds " % ("%",(indent-2))
                        fm1 = getattr(fm,subitem)
                        if type(fm1) == types.MethodType:
                            line += colour(yellow,fmt % subitem) #+ '(method)      '
                            result, diff = checkMethod(fm1,item)
                            line += result
                            if diff: difference += " " + diff
                        elif type(fm1) == types.FunctionType:
                            line += colour(yellow+bright,fmt % subitem) #+ '(staticmethod)'
                            line += checkStaticMethod(fm1,item)
                        else: # class data, should add check
                            line += colour(red+bright,fmt % subitem) #+ '(class data)'
                            line += "     (not checked)"
                        if line:
                            print line
                            if difference:
                                print " "*10 + difference
                        if verbose:
                            if inconsistency: print inconsistency.strip("\n")
                            inconsistency = ""
            else: # data
                line = colour(bright+red,fmt % item) #+ '(data)        '
                line += checkData(item)
            if line:
                print line
                if difference:
                    print " "*10 + difference
            if verbose:
                if inconsistency: print inconsistency.strip("\n")
                inconsistency = ""
    print "\n%s%s" % (" "*(indent+3),header)
