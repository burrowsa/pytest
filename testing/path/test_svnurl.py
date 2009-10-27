import py
from _py.path.svnurl import InfoSvnCommand
import datetime
import time
from testing.path.svntestbase import CommonSvnTests

def pytest_funcarg__path1(request):
    repo, wc = request.getfuncargvalue("repowc1")
    return py.path.svnurl(repo)

class TestSvnURLCommandPath(CommonSvnTests):
    @py.test.mark.xfail
    def test_load(self, path1):
        super(TestSvnURLCommandPath, self).test_load(path1)

    def test_move_file(self, path1):  # overrides base class
        p = path1.ensure('origfile')
        newp = p.dirpath('newfile')
        p.move(newp)
        assert newp.check(file=1)
        newp.remove()
        assert not p.check()

    def test_move_dir(self, path1):  # overrides base class
        p = path1.ensure('origdir', dir=1)
        newp = p.dirpath('newdir')
        p.move(newp)
        assert newp.check(dir=1)
        newp.remove()
        assert not p.check()

    def test_svnurl_needs_arg(self, path1):
        py.test.raises(TypeError, "py.path.svnurl()")

    def test_svnurl_does_not_accept_None_either(self, path1):
        py.test.raises(Exception, "py.path.svnurl(None)")

    def test_svnurl_characters_simple(self, path1):
        py.path.svnurl("svn+ssh://hello/world")

    def test_svnurl_characters_at_user(self, path1):
        py.path.svnurl("http://user@host.com/some/dir")

    def test_svnurl_characters_at_path(self, path1):
        py.test.raises(ValueError, 'py.path.svnurl("http://host.com/foo@bar")')

    def test_svnurl_characters_colon_port(self, path1):
        py.path.svnurl("http://host.com:8080/some/dir")

    def test_svnurl_characters_tilde_end(self, path1):
        py.path.svnurl("http://host.com/some/file~")

    @py.test.mark.xfail("sys.platform == 'win32'")
    def test_svnurl_characters_colon_path(self, path1):
        # colons are allowed on win32, because they're part of the drive
        # part of an absolute path... however, they shouldn't be allowed in
        # other parts, I think
        py.test.raises(ValueError, 'py.path.svnurl("http://host.com/foo:bar")')

    def test_export(self, path1, tmpdir):
        tmpdir = tmpdir.join("empty")
        p = path1.export(tmpdir)
        assert p == tmpdir # XXX should return None
        n1 = [x.basename for x in tmpdir.listdir()]
        n2 = [x.basename for x in path1.listdir()]
        n1.sort()
        n2.sort()
        assert n1 == n2 
        assert not p.join('.svn').check()
        rev = path1.mkdir("newdir")
        tmpdir.remove()
        assert not tmpdir.check()
        path1.new(rev=1).export(tmpdir)
        for p in tmpdir.listdir():
            assert p.basename in n2

class TestSvnInfoCommand:

    def test_svn_1_2(self):
        line = "   2256      hpk        165 Nov 24 17:55 __init__.py"
        info = InfoSvnCommand(line)
        now = datetime.datetime.now()
        assert info.last_author == 'hpk'
        assert info.created_rev == 2256
        assert info.kind == 'file'
        # we don't check for the year (2006), because that depends
        # on the clock correctly being setup
        assert time.gmtime(info.mtime)[1:6] == (11, 24, 17, 55, 0)
        assert info.size ==  165
        assert info.time == info.mtime * 1000000

    def test_svn_1_3(self):
        line ="    4784 hpk                 2 Jun 01  2004 __init__.py"
        info = InfoSvnCommand(line)
        assert info.last_author == 'hpk'
        assert info.kind == 'file'

    def test_svn_1_3_b(self):
        line ="     74 autoadmi              Oct 06 23:59 plonesolutions.com/"
        info = InfoSvnCommand(line)
        assert info.last_author == 'autoadmi'
        assert info.kind == 'dir'

def test_badchars():
    py.test.raises(ValueError, "py.path.svnurl('http://host/tmp/@@@:')")