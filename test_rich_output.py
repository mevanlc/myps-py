#!/usr/bin/env python3
"""Test script to demonstrate the rich styling in myps"""

from rich.console import Console
from rich.text import Text

console = Console()

# Simulate a few lines of myps output with the new styling
examples = [
    ("bash", "1234", "/bin/bash -l"),
    ("  python", "5678", "python script.py --verbose --config=prod.ini"),
    ("    node", "9012", "node server.js --port 3000"),
    ("zsh", "3456", "/bin/zsh -i"),
    ("  vim", "7890", "vim /path/to/some/very/long/file/name/that/shows/the/command/line.py"),
]

print("\n=== Rich styled output (what you'll see in terminal): ===\n")

for name, pid, cmdline in examples:
    text = Text()
    # Extract indent
    indent_len = len(name) - len(name.lstrip())
    indent = " " * indent_len
    name_stripped = name.lstrip()

    text.append(indent)
    text.append(name_stripped, style="bold cyan")
    text.append(" ")
    text.append(pid, style="yellow")
    text.append(" ")
    text.append(cmdline, style="dim")
    console.print(text, highlight=False)

print("\n=== Plain output (for comparison): ===\n")

for name, pid, cmdline in examples:
    print(f"{name} {pid} {cmdline}")

print("\n=== Color legend: ===")
console.print("• Process names: [bold cyan]bold cyan[/bold cyan]")
console.print("• PIDs: [yellow]yellow[/yellow]")
console.print("• Command lines: [dim]dim (reduced intensity)[/dim]")