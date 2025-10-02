import typing

from psutil import AccessDenied, Process, ZombieProcess
from psutil import _as_dict_attrnames as __as_dict_attrnames  # type: ignore

_as_dict_attrnames = ["pid"] + list(
    typing.cast(set[str], __as_dict_attrnames) - {"pid"}
)

ProcessDictType = dict[str, "ProcessDictValueType"]
ProcessDictValueType = (
    ProcessDictType
    | list[ProcessDictType]
    | list["ProcessDictValueType"]
    | int
    | bool
    | str
    | float
    | None
)


def process_as_dict(
    process: Process,
    attrs: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None = None,
    ad_value: str | None = "⛔️",
    zp_value: str | None = "🧟",
) -> ProcessDictType:
    """Utility method returning process information as a hashable dictionary.
    If *attrs* is specified it must be a list of strings reflecting available Process class' attribute names
        (e.g. ['cpu_times', 'name']) else all public (read only) attributes are assumed.
    *ad_value* is the value which gets assigned in case AccessDenied exception is raised when retrieving that particular process information.
    *zp_value* is the value which gets assigned in case ZombieProcess exception is raised when retrieving that particular process information.
    """
    if attrs is not None:
        valid_names = set(_as_dict_attrnames)
        invalid_names = set(attrs) - valid_names
        if invalid_names:
            msg = "invalid attr name{} {}".format(
                "s" if len(invalid_names) > 1 else "",
                ", ".join(map(repr, invalid_names)),
            )
            raise ValueError(msg)

    retdict: ProcessDictType = {}
    ls = attrs or _as_dict_attrnames
    with process.oneshot():
        for name in ls:
            try:
                if name == "pid":
                    ret = process.pid
                else:
                    meth = getattr(process, name)
                    ret = meth()
            except AccessDenied:
                ret = ad_value
            except ZombieProcess:
                ret = zp_value
            except NotImplementedError:
                # in case of not implemented functionality (may happen
                # on old or exotic systems) we want to crash only if
                # the user explicitly asked for that particular attr
                if attrs:
                    raise
                continue
            retdict[name] = ret
    return retdict


if __name__ == "__main__":
    import json
    import sys

    import psutil

    pids = psutil.pids()
    procs: list[ProcessDictType] = []
    for pid in pids:
        try:
            p = psutil.Process(pid)
            procs.append(process_as_dict(p))
        except psutil.NoSuchProcess:
            pass
    print("[")
    for i, proc in enumerate(procs, start=1):
        print("  ", end="")
        json.dump(proc, sys.stdout, ensure_ascii=False)
        if i < len(procs):
            print(",")
    print("]")
