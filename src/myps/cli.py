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

from . import pstree
from .psprinter import PSTreePrinter
from .pstree import PSTree

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

TRUNC_INDICATOR = "…"

def main():
    parser = argparse.ArgumentParser(epilog="<Epilog>")
    parser.add_argument('-f', '--full', action='store_true', help='Disable terminal-width truncation')
    parser.add_argument('-r', '--regex', action='store_true', help='Interpret pattern as a regular expression')
    parser.add_argument('-c', '--case', action='store_true', help='Case-sensitive pattern matching (default is case-insensitive)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output for debugging')
    parser.add_argument('-k', '--keep-ancestors', action='store_true', help='Keep ancestor of processes matching pattern')
    parser.add_argument('filter', nargs='?', default='', help='Pattern to filter processes by', metavar='PATTERN', dest='filter_pattern')
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
        if pstree.safe_get_pid(proc) == thispid:
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
    myproc_pids = {pstree.safe_get_pid(p) for p in myprocs}
    for proc in myprocs:
        ppid = pstree.safe_get_ppid(proc)
        if ppid not in myproc_pids:
            missing_parents.add(ppid)
    for missing_parent_pid in missing_parents:
        parent_proc = pstree.safe_get_process(missing_parent_pid)
        if parent_proc:
            myprocs.append(parent_proc)

    re_pattern: re.Pattern[str] | None = None
    if args.filter_pattern:
        flags = 0 if args.case else re.IGNORECASE
        if args.regex:
            re_pattern = re.compile(args.filter_pattern, flags)
        else:
            pattern = fnmatch.translate(args.filter_pattern)
            if pattern[-2:].lower() == r'\z':
                pattern = pattern[:-2]
            re_pattern = re.compile(pattern, flags)

    if args.verbose:
        if args.filter_pattern:
            print(f"Pattern: {args.filter_pattern!r}, Regex: {args.regex}, Case: {args.case}")
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
                print(PSTreePrinter.truncate_line(ln, term_width))
        if args.verbose and re_pattern:
            print(f"Matched lines: {len(lines)}")
    else:
        print("No matching processes found for current user.")


def build_proc_graph(processes: list[Process]) -> tuple[list[Process], dict[int, list[Process]]]:
    # Backward-compat shim for prior function; now delegates to PSTree
    tree = pstree.PSTree.from_processes(processes)
    return tree.roots, tree.children_map

def build_tree(
    roots: list[Process],
    children_map: dict[int, list[Process]]
) -> list[str]:
    # Backward-compat helper, now implemented via PSTreePrinter
    tree = pstree.PSTree(roots=roots, children_map=children_map)
    printer = PSTreePrinter(tree)
    lines, _ = printer.build_all_lines_with_map(use_rich=False)
    return [str(line) for line in lines]


VALID_PYTHON_PRINT_KWARGS = {"sep", "end", "file", "flush"}


# FYI rich.Console.print has this signature:
# @overload
# def print(
#     *values: object, sep: str | None = " ", end: str | None = "\n", file: SupportsWrite[str] | None = None, flush: Literal[False] = False,
# ) -> None: ...
# @overload
# def print(
#     *values: object, sep: str | None = " ", end: str | None = "\n", file: _SupportsWriteAndFlush[str] | None = None, flush: bool
# ) -> None: ...
@wraps(Console.print, assigned=("__signature__",))
def console_print(*args: object, **kwargs: object) -> None:
    global console
    if console is None:
        fwd_kwargs = {k: v for k, v in kwargs.items() if k in VALID_PYTHON_PRINT_KWARGS}
        print(*args, **fwd_kwargs) # type: ignore
    else:
        console.print(*args, **kwargs) # type: ignore

class CliArgs:
    full: bool = False
    regex: bool = False
    filter_pattern: str = ""
    case: bool = False
    verbose: bool = False
    keep_ancestors: bool = False

if __name__ == "__main__":
    main()
