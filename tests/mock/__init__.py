# Mocking library for module and code injection, replay tests and other
# unit testing purposes
#
# Copyright (C) 2010
# Red Hat, Inc.  All rights reserved.
#
# Author(s): Martin Sivak <msivak@redhat.com>


from disk import *
from mock import *
import unittest

def slow(f):
    """Decorates a test method as being slow, usefull for python-nose filtering"""
    f.slow = True
    return f

def acceptance(f):
    """Decorates test as belonging to acceptance testing and not useable in common devellopment unit testing. To be used with python-nose filtering."""
    f.acceptance = True
    return f

class TestCase(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)
        self.injectedModules = {}

    def setupModules(self, a):
        """Mock specified list of modules and store the list so it can be
           properly unloaded during tearDown"""

        import sys
        self.preexistingModules = set(sys.modules.keys())

        for m in a:
            sys.modules[m] = Mock()
            self.injectedModules[m] = sys.modules[m]

    def modifiedModule(self, mname, mod = None):
        """Mark module (and all it's parents) as tainted"""

        oldname=""
        for m in mname.split("."):
            self.injectedModules[oldname+m] = mod
            oldname += m + "."
        self.injectedModules[mname] = mod    

    def tearDownModules(self):
        """Unload previously Mocked modules"""

        import sys

        for m in sys.modules.keys():
            if m in self.preexistingModules and not m in self.injectedModules:
                continue

            del sys.modules[m]
