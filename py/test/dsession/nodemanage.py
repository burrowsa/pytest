import py
import sys, os
from py.__.test.dsession.txnode import MasterNode
from py.__.execnet.gwmanage import GatewayManager

    
class NodeManager(object):
    def __init__(self, config, specs=None):
        self.config = config 
        if specs is None:
            specs = self.config.getxspecs()
        self.roots = self.config.getrsyncdirs()
        self.gwmanager = GatewayManager(specs)
        self.nodes = []

    def trace(self, msg):
        self.config.bus.notify("trace", "nodemanage", msg)

    def trace_nodestatus(self):
        if self.config.option.debug:
            for ch, result in self.gwmanager.multi_exec("""
                import sys, os
                channel.send((sys.executable, os.getcwd(), sys.path))
            """).receive_each(withchannel=True):
                self.trace("spec %r, execuable %r, cwd %r, syspath %r" %(
                    ch.gateway.spec, result[0], result[1], result[2]))

    def config_getignores(self):
        return self.config.getconftest_pathlist("rsyncignore")

    def rsync_roots(self):
        """ make sure that all remote gateways
            have the same set of roots in their
            current directory. 
        """
        self.makegateways()
        options = {
            'ignores': self.config_getignores(), 
            'verbose': self.config.option.verbose,
        }
        if self.roots:
            # send each rsync root
            for root in self.roots:
                self.gwmanager.rsync(root, **options)
        else: 
            XXX # do we want to care for situations without explicit rsyncdirs? 
            # we transfer our topdir as the root
            self.gwmanager.rsync(self.config.topdir, **options)
            # and cd into it 
            self.gwmanager.multi_chdir(self.config.topdir.basename, inplacelocal=False)

    def makegateways(self):
        # we change to the topdir sot that 
        # PopenGateways will have their cwd 
        # such that unpickling configs will 
        # pick it up as the right topdir 
        # (for other gateways this chdir is irrelevant)
        old = self.config.topdir.chdir()  
        try:
            self.gwmanager.makegateways()
        finally:
            old.chdir()
        self.trace_nodestatus()


    def setup_nodes(self, putevent):
        self.rsync_roots()
        nice = self.config.getvalue("dist_nicelevel")
        if nice != 0:
            self.gwmanager.multi_exec("""
                import os
                if hasattr(os, 'nice'): 
                    os.nice(%r)
            """ % nice).waitclose()

        self.trace_nodestatus()
        multigw = self.gwmanager.getgateways(inplacelocal=False, remote=True)
        multigw.remote_exec("""
            import os, sys
            sys.path.insert(0, os.getcwd())
        """).waitclose()

        for gateway in self.gwmanager.gateways:
            node = MasterNode(gateway, self.config, putevent)
            self.nodes.append(node) 

    def teardown_nodes(self):
        # XXX teardown nodes? 
        self.gwmanager.exit()

