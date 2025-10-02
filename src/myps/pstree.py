import os

import psutil
from psutil import Process


def proc_key(proc: Process) -> tuple[str, int]:
    exe = safe_get_exe(proc)
    pid = safe_get_pid(proc)
    return (exe, pid)


def is_same_exe(cmdline: list[str], exe: str) -> bool:
    if not cmdline:
        return False
    real_cmdline_exe = os.path.realpath(cmdline[0])
    real_exe = os.path.realpath(exe)
    return real_cmdline_exe == real_exe


def safe_get_cmdline(proc: Process) -> str:
    try:
        cmdline = proc.cmdline()
        exe = safe_get_exe(proc)
        if not is_same_exe(cmdline, exe):
            cmdline = [f"<{exe}>"] + cmdline
        return " ".join(str(c) for c in cmdline).strip()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""

def safe_get_process(pid: int) -> Process | None:
    try:
        return psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None

def safe_get_pid(proc: Process) -> int:
    try:
        return proc.pid
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return 0

def safe_get_ppid(proc: Process) -> int:
    try:
        return proc.ppid()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return 0

def safe_get_exe(proc: Process) -> str:
    try:
        return proc.exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""
    
def safe_get_name(proc: Process) -> str:
    try:
        return proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""


class PSTree:
    def __init__(self, *, roots: list[Process], children_map: dict[int, list[Process]]):
        self.roots = roots
        self.children_map = children_map
        # Build parent map for quick ancestor lookups
        parent_map: dict[int, int] = {}
        for parent, kids in children_map.items():
            for child in kids:
                parent_map[safe_get_pid(child)] = parent
        self.parent_map = parent_map

    @classmethod
    def from_processes(cls, processes: list[Process]) -> "PSTree":
        # Map pid -> process and parent -> [children]
        pid_map: dict[int, Process] = {}
        for p in processes:
            pid = safe_get_pid(p)
            if pid:
                pid_map[pid] = p

        children_map: dict[int, list[Process]] = {pid: [] for pid in pid_map.keys()}

        for pid, p in list(pid_map.items()):
            ppid = safe_get_ppid(p)
            if ppid in pid_map:
                children_map[ppid].append(p)

        # Roots are those whose parent is not in the kept set
        roots: list[Process] = []
        for pid, p in pid_map.items():
            ppid = safe_get_ppid(p)
            if ppid not in pid_map:
                roots.append(p)

        # Sort children lists for stable output
        for kids in children_map.values():
            kids.sort(key=proc_key)

        roots.sort(key=proc_key)
        return cls(roots=roots, children_map=children_map)

    def include_with_ancestors(self, base_pids: set[int]) -> set[int]:
        """Return a set with base pids plus all their ancestors up to roots."""
        include: set[int] = set()
        for pid in base_pids:
            cur = pid
            while cur and cur not in include:
                include.add(cur)
                cur = self.parent_map.get(cur, 0)
        return include
    
