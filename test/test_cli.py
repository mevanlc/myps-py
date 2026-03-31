import os
import sys

import pytest

from myps import cli, psprinter, pssafe


class StubProcess:
    def __init__(self, pid: int, exe: str, uids: tuple[int, int, int], ppid: int):
        self.pid = pid
        self._exe = exe
        self._uids = uids
        self._ppid = ppid
        self._cmdline = [exe]
        self._name = os.path.basename(exe) or f"proc{pid}"

    def uids(self):
        return self._uids

    def exe(self):
        return self._exe

    def ppid(self):
        return self._ppid

    def cmdline(self):
        return list(self._cmdline)

    def name(self):
        return self._name


@pytest.fixture(autouse=True)
def restore_cli_args():
    original = list(sys.argv)
    try:
        yield
    finally:
        sys.argv = original


def test_cli_init_config(tmp_path, monkeypatch, capsys):
    target = tmp_path / "init.toml"
    sys.argv = ["myps", "--init-config", "-c", str(target)]
    rc = cli.cli_main()
    assert rc == 0
    assert target.exists()

    sys.argv = ["myps", "--init-config", "-c", str(target)]
    rc = cli.cli_main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "already exists" in err


def test_cli_filters_respect_config(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "cfg.toml"
    config_path.write_text(
        """
[regexSkipPatterns]
system = '^/System/'

[regexKeepPatterns]
terminal = 'Terminal.app/'
        """.strip()
    )

    user_uid = 501
    terminal_proc = StubProcess(
        pid=200,
        exe="/Applications/Utilities/Terminal.app/MacOS/Terminal",
        uids=(user_uid, user_uid, user_uid),
        ppid=1,
    )
    system_proc = StubProcess(
        pid=300,
        exe="/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder",
        uids=(user_uid, user_uid, user_uid),
        ppid=1,
    )
    parent_proc = StubProcess(
        pid=1,
        exe="/sbin/launchd",
        uids=(user_uid, user_uid, user_uid),
        ppid=0,
    )

    procs = [terminal_proc, system_proc]
    proc_map = {p.pid: p for p in procs + [parent_proc]}

    monkeypatch.setattr(os, "getuid", lambda: user_uid)
    monkeypatch.setattr(cli.psutil, "process_iter", lambda: iter(procs))
    monkeypatch.setattr(pssafe, "safe_get_process", lambda pid: proc_map.get(pid))
    monkeypatch.setattr(
        psprinter.RichProcess, "is_argv0_equal_to_exe", lambda self: True
    )

    sys.argv = [
        "myps",
        "--full",
        "--color",
        "never",
        "-c",
        str(config_path),
    ]

    rc = cli.cli_main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "Terminal" in out
    assert "Finder" not in out


def test_main_propagates_unexpected_exceptions(monkeypatch):
    class Boom(Exception):
        pass

    monkeypatch.setattr(cli, "cli_main", lambda: (_ for _ in ()).throw(Boom("boom")))

    with pytest.raises(Boom, match="boom"):
        cli.main()


def test_rich_process_mismatch_renders_exe_instead_of_raising():
    proc = StubProcess(
        pid=123,
        exe="/opt/homebrew/libexec/git-core/git-remote-http",
        uids=(501, 501, 501),
        ppid=1,
    )
    proc._name = "git-remote-https"
    proc._cmdline = ["/opt/homebrew/opt/git/libexec/git-core/git-remote-https"]

    rendered = psprinter.RichProcess(proc).__rich__().plain

    assert "git-remote-https 123" in rendered
    assert "</opt/homebrew/libexec/git-core/git-remote-http>" in rendered
    assert "/opt/homebrew/opt/git/libexec/git-core/git-remote-https" in rendered
