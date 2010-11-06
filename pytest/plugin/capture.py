""" per-test stdout/stderr capturing mechanisms, ``capsys`` and ``capfd`` function arguments.  """

import py
import os

def pytest_addoption(parser):
    group = parser.getgroup("general")
    group._addoption('--capture', action="store", default=None,
        metavar="method", type="choice", choices=['fd', 'sys', 'no'],
        help="per-test capturing method: one of fd (default)|sys|no.")
    group._addoption('-s', action="store_const", const="no", dest="capture",
        help="shortcut for --capture=no.")

def addouterr(rep, outerr):
    repr = getattr(rep, 'longrepr', None)
    if not hasattr(repr, 'addsection'):
        return
    for secname, content in zip(["out", "err"], outerr):
        if content:
            repr.addsection("Captured std%s" % secname, content.rstrip())

def pytest_configure(config):
    config.pluginmanager.register(CaptureManager(), 'capturemanager')

def pytest_unconfigure(config):
    capman = config.pluginmanager.getplugin('capturemanager')
    while capman._method2capture:
        name, cap = capman._method2capture.popitem()
        cap.reset()

class NoCapture:
    def startall(self):
        pass
    def resume(self):
        pass
    def reset(self):
        pass
    def suspend(self):
        return "", ""

class CaptureManager:
    def __init__(self):
        self._method2capture = {}

    def _maketempfile(self):
        f = py.std.tempfile.TemporaryFile()
        newf = py.io.dupfile(f, encoding="UTF-8")
        f.close()
        return newf

    def _makestringio(self):
        return py.io.TextIO()

    def _getcapture(self, method):
        if method == "fd":
            return py.io.StdCaptureFD(now=False,
                out=self._maketempfile(), err=self._maketempfile()
            )
        elif method == "sys":
            return py.io.StdCapture(now=False,
                out=self._makestringio(), err=self._makestringio()
            )
        elif method == "no":
            return NoCapture()
        else:
            raise ValueError("unknown capturing method: %r" % method)

    def _getmethod(self, config, fspath):
        if config.option.capture:
            method = config.option.capture
        else:
            try:
                method = config._conftest.rget("option_capture", path=fspath)
            except KeyError:
                method = "fd"
        if method == "fd" and not hasattr(os, 'dup'): # e.g. jython
            method = "sys"
        return method

    def resumecapture_item(self, item):
        method = self._getmethod(item.config, item.fspath)
        if not hasattr(item, 'outerr'):
            item.outerr = ('', '') # we accumulate outerr on the item
        return self.resumecapture(method)

    def resumecapture(self, method):
        if hasattr(self, '_capturing'):
            raise ValueError("cannot resume, already capturing with %r" %
                (self._capturing,))
        cap = self._method2capture.get(method)
        self._capturing = method
        if cap is None:
            self._method2capture[method] = cap = self._getcapture(method)
            cap.startall()
        else:
            cap.resume()

    def suspendcapture(self, item=None):
        self.deactivate_funcargs()
        if hasattr(self, '_capturing'):
            method = self._capturing
            cap = self._method2capture.get(method)
            if cap is not None:
                outerr = cap.suspend()
            del self._capturing
            if item:
                outerr = (item.outerr[0] + outerr[0],
                          item.outerr[1] + outerr[1])
            return outerr
        if hasattr(item, 'outerr'):
            return item.outerr
        return "", ""

    def activate_funcargs(self, pyfuncitem):
        if not hasattr(pyfuncitem, 'funcargs'):
            return
        assert not hasattr(self, '_capturing_funcargs')
        self._capturing_funcargs = capturing_funcargs = []
        for name, capfuncarg in pyfuncitem.funcargs.items():
            if name in ('capsys', 'capfd'):
                capturing_funcargs.append(capfuncarg)
                capfuncarg._start()

    def deactivate_funcargs(self):
        capturing_funcargs = getattr(self, '_capturing_funcargs', None)
        if capturing_funcargs is not None:
            while capturing_funcargs:
                capfuncarg = capturing_funcargs.pop()
                capfuncarg._finalize()
            del self._capturing_funcargs

    def pytest_make_collect_report(self, __multicall__, collector):
        method = self._getmethod(collector.config, collector.fspath)
        try:
            self.resumecapture(method)
        except ValueError:
            return # recursive collect, XXX refactor capturing
                   # to allow for more lightweight recursive capturing
        try:
            rep = __multicall__.execute()
        finally:
            outerr = self.suspendcapture()
        addouterr(rep, outerr)
        return rep

    def pytest_runtest_setup(self, item):
        self.resumecapture_item(item)

    def pytest_runtest_call(self, item):
        self.resumecapture_item(item)
        self.activate_funcargs(item)

    def pytest_runtest_teardown(self, item):
        self.resumecapture_item(item)

    def pytest__teardown_final(self, __multicall__, session):
        method = self._getmethod(session.config, None)
        self.resumecapture(method)
        try:
            rep = __multicall__.execute()
        finally:
            outerr = self.suspendcapture()
        if rep:
            addouterr(rep, outerr)
        return rep

    def pytest_keyboard_interrupt(self, excinfo):
        if hasattr(self, '_capturing'):
            self.suspendcapture()

    def pytest_runtest_makereport(self, __multicall__, item, call):
        self.deactivate_funcargs()
        rep = __multicall__.execute()
        outerr = self.suspendcapture(item)
        if not rep.passed:
            addouterr(rep, outerr)
        if not rep.passed or rep.when == "teardown":
            outerr = ('', '')
        item.outerr = outerr
        return rep

def pytest_funcarg__capsys(request):
    """captures writes to sys.stdout/sys.stderr and makes
    them available successively via a ``capsys.readouterr()`` method
    which returns a ``(out, err)`` tuple of captured snapshot strings.
    """
    return CaptureFuncarg(py.io.StdCapture)

def pytest_funcarg__capfd(request):
    """captures writes to file descriptors 1 and 2 and makes
    snapshotted ``(out, err)`` string tuples available
    via the ``capsys.readouterr()`` method.  If the underlying
    platform does not have ``os.dup`` (e.g. Jython) tests using
    this funcarg will automatically skip.
    """
    if not hasattr(os, 'dup'):
        py.test.skip("capfd funcarg needs os.dup")
    return CaptureFuncarg(py.io.StdCaptureFD)

class CaptureFuncarg:
    def __init__(self, captureclass):
        self.capture = captureclass(now=False)

    def _start(self):
        self.capture.startall()

    def _finalize(self):
        if hasattr(self, 'capture'):
            self.capture.reset()
            del self.capture

    def readouterr(self):
        return self.capture.readouterr()

    def close(self):
        self._finalize()
