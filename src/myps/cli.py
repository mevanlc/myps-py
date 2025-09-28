#!/usr/bin/env python3

# pyright: strict

import argparse
import fnmatch
import os
import re
import shutil
import sys
from functools import wraps
from typing import Iterator

import psutil
from psutil import Process
from rich.console import Console
from rich.text import Text

PATTERN_SKIP = re.compile('|'.join([
    r"^/System/",
    r"^/usr/sbin/",
    r"^/usr/libexec/",
    r"^/Applications/",
    r"^/Library/",
    r"/httpd$",
    r"/php-fpm$"
]))
PATTERN_KEEP = re.compile('|'.join([
    r"/Applications/iTerm2?.app/",
    r"/Applications/Utilities/Terminal.app/",
    r"[Xx][Cc]ode"
]))

console: Console | None = None

# @overload
# def print(
#     *values: object, sep: str | None = " ", end: str | None = "\n", file: SupportsWrite[str] | None = None, flush: Literal[False] = False,
# ) -> None: ...
# @overload
# def print(
#     *values: object, sep: str | None = " ", end: str | None = "\n", file: _SupportsWriteAndFlush[str] | None = None, flush: bool
# ) -> None: ...
VALID_PRINT_KWARGS = {"sep", "end", "file", "flush"}
@wraps(Console.print, assigned=("__signature__",))
def console_print(*args: object, **kwargs: object) -> None:
    global console
    if console is None:
        fwd_kwargs = {k: v for k, v in kwargs.items() if k in VALID_PRINT_KWARGS}
        print(*args, **fwd_kwargs) # type: ignore
    else:
        console.print(*args, **kwargs) # type: ignore


TRUNC_INDICATOR = "…"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--full', action='store_true', help='Disable terminal-width truncation')
    parser.add_argument('-r', '--regex', action='store_true', help='Interpret pattern as a regular expression')
    parser.add_argument('-c', '--case', action='store_true', help='Case-sensitive pattern matching (default is case-insensitive)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output for debugging')
    parser.add_argument('-k', '--keep-ancestors', action='store_true', help='Keep ancestor of processes matching pattern')
    parser.add_argument('pattern', nargs='?', default='', help='Pattern to filter processes by')
    args = parser.parse_args(namespace=CliArgs())
    if args.full or not sys.stdout.isatty():
        term_width = 0
    else:
        term_width = shutil.get_terminal_size((80, 20)).columns

    myuid = os.getuid()
    thispid = os.getpid()

    myprocs: list[Process] = []
    proc_iter: Iterator[Process] = (
        psutil.process_iter() # type: ignore
    )
    for proc in proc_iter:
        if safe_get_pid(proc) == thispid:
            continue
        try:
            uids = proc.uids()
            if myuid in uids:
                exe = proc.exe()
                should_skip = PATTERN_SKIP.search(exe) and not PATTERN_KEEP.search(exe)
                if should_skip:
                    continue
                myprocs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    missing_parents: set[int] = set()
    myproc_pids = {safe_get_pid(p) for p in myprocs}
    for proc in myprocs:
        ppid = safe_get_ppid(proc)
        if ppid not in myproc_pids:
            missing_parents.add(ppid)
    for missing_parent_pid in missing_parents:
        parent_proc = safe_get_process(missing_parent_pid)
        if parent_proc:
            myprocs.append(parent_proc)

    re_pattern: re.Pattern[str] | None = None
    if args.pattern:
        flags = 0 if args.case else re.IGNORECASE
        if args.regex:
            re_pattern = re.compile(args.pattern, flags)
        else:
            pattern = fnmatch.translate(args.pattern)
            if pattern[-2:].lower() == r'\z':
                pattern = pattern[:-2]
            re_pattern = re.compile(pattern, flags)

    if args.verbose:
        if args.pattern:
            print(f"Pattern: {args.pattern!r}, Regex: {args.regex}, Case: {args.case}")
            print(f"Compiled regex: {re_pattern.pattern if re_pattern else 'None'}")
        print(f"Total processes for user {myuid}: {len(myprocs)}")

    if myprocs:
        tree = PSTree.from_processes(myprocs)
        printer = PSTreePrinter(tree)
        console = Console()
        use_rich_output = sys.stdout.isatty()  # Only use rich styling for terminal output

        # Build full pre-order traversal once so we can both search and print
        full_lines, pid_to_line = printer.build_all_lines_with_map(use_rich=use_rich_output)

        if re_pattern:
            if args.keep_ancestors:
                # Identify matching PIDs by searching their full formatted line
                matching_pids: set[int] = set()
                for pid, line in pid_to_line.items():
                    search_text = line.plain
                    if re_pattern.search(search_text):
                        matching_pids.add(pid)

                include_pids = tree.include_with_ancestors(matching_pids)
                lines = printer.build_lines_for_include(include_pids, use_rich=use_rich_output)
            else:
                lines = [ln for ln in full_lines if re_pattern.search(ln.plain)]
        else:
            lines = full_lines

        for ln in lines:
            if use_rich_output:
                # For rich output, truncate and print with console
                if term_width:
                    ln.truncate(term_width, overflow="ellipsis")
                console.print(ln, highlight=False)
            else:
                print(truncate_line(ln, term_width))
        if args.verbose and re_pattern:
            print(f"Matched lines: {len(lines)}")
    else:
        print("No matching processes found for current user.")

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


def proc_key(proc: Process) -> tuple[str, int]:
    exe = safe_get_exe(proc)
    pid = safe_get_pid(proc)
    return (exe, pid)


def build_proc_graph(processes: list[Process]) -> tuple[list[Process], dict[int, list[Process]]]:
    # Backward-compat shim for prior function; now delegates to PSTree
    tree = PSTree.from_processes(processes)
    return tree.roots, tree.children_map

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


def fmt_line(proc: Process, indent_level: int, use_rich: bool = False) -> Text:
    indent = "  " * indent_level
    name = safe_get_name(proc)
    pid = safe_get_pid(proc)
    cmdline = safe_get_cmdline(proc)

    

    if use_rich:
        text = Text()
        text.append(indent)
        text.append(name, style="bold cyan")
        text.append(" ")
        text.append(str(pid), style="yellow")
        text.append(" ")
        text.append(cmdline, style="dim")
        return_value: Text =  text
    else:
        s = f"{indent}{name} {pid} {cmdline}"
        return_value: Text = Text(s)
    return return_value


def truncate_line(line: Text, max_length: int) -> Text:
    line.truncate(max_length, overflow="ellipsis")
    return line

def build_tree(
    roots: list[Process],
    children_map: dict[int, list[Process]]
) -> list[str]:
    # Backward-compat helper, now implemented via PSTreePrinter
    tree = PSTree(roots=roots, children_map=children_map)
    printer = PSTreePrinter(tree)
    lines, _ = printer.build_all_lines_with_map(use_rich=False)
    return [str(line) for line in lines]

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

class PSTreePrinter:
    def __init__(self, tree: PSTree):
        self.tree = tree

    def build_all_lines_with_map(self, use_rich: bool = False) -> tuple[list[Text], dict[int, Text]]:
        lines: list[Text] = []
        pid_to_line: dict[int, Text] = {}

        def walk(proc: Process, depth: int) -> None:
            line = fmt_line(proc, depth, use_rich=use_rich)
            lines.append(line)
            pid_to_line[safe_get_pid(proc)] = line
            for child in self.tree.children_map.get(proc.pid, []):
                walk(child, depth + 1)

        for root in self.tree.roots:
            walk(root, 0)
        return lines, pid_to_line

    def build_lines_for_include(self, include_pids: set[int], use_rich: bool = False) -> list[Text]:
        lines: list[Text] = []

        def walk(proc: Process, depth: int) -> None:
            pid = safe_get_pid(proc)
            if pid in include_pids:
                lines.append(fmt_line(proc, depth, use_rich=use_rich))
                for child in self.tree.children_map.get(proc.pid, []):
                    walk(child, depth + 1)
            else:
                # If parent not included, still might have included descendants.
                for child in self.tree.children_map.get(proc.pid, []):
                    walk(child, depth + 1)

        for root in self.tree.roots:
            walk(root, 0)
        return lines

class CliArgs:
    full: bool = False
    regex: bool = False
    pattern: str = ""
    case: bool = False
    verbose: bool = False
    keep_ancestors: bool = False

if __name__ == "__main__":
    main()
