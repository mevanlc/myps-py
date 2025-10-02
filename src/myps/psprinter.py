from psutil import Process
from rich.text import Text

from .pstree import PSTree, safe_get_cmdline, safe_get_name, safe_get_pid


class PSTreePrinter:
    def __init__(self, tree: PSTree):
        self.tree = tree

    def build_all_lines_with_map(self, use_rich: bool = False) -> tuple[list[Text], dict[int, Text]]:
        lines: list[Text] = []
        pid_to_line: dict[int, Text] = {}

        def walk(proc: Process, depth: int) -> None:
            line = self.fmt_line(proc, depth, use_rich=use_rich)
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
                lines.append(self.fmt_line(proc, depth, use_rich=use_rich))
                for child in self.tree.children_map.get(proc.pid, []):
                    walk(child, depth + 1)
            else:
                # If parent not included, still might have included descendants.
                for child in self.tree.children_map.get(proc.pid, []):
                    walk(child, depth + 1)

        for root in self.tree.roots:
            walk(root, 0)
        return lines


    @staticmethod
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

    @staticmethod
    def truncate_line(line: Text, max_length: int) -> Text:
        line.truncate(max_length, overflow="ellipsis")
        return line
