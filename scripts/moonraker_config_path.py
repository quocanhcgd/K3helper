#!/usr/bin/env python3
"""Locate the persistent Moonraker config used by the running K3 service."""

import glob
import os
import sys


DEFAULT_CANDIDATES = (
    "/mnt/SDCARD/cxsw/printer_data/config/moonraker.conf",
    "/mnt/UDISK/moonraker.conf",
    "/mnt/UDISK/printer_data/config/moonraker.conf",
)
CONFIG_OPTIONS = ("-c", "--configfile", "--config-file")


def process_config(proc_root="/proc"):
    for cmdline in glob.glob(os.path.join(proc_root, "[0-9]*", "cmdline")):
        try:
            with open(cmdline, "rb") as source:
                args = [arg.decode("utf-8", "replace") for arg in source.read().split(b"\0") if arg]
        except OSError:
            continue
        if not any("moonraker" in os.path.basename(arg).lower() for arg in args):
            continue
        for index, arg in enumerate(args):
            if arg in CONFIG_OPTIONS and index + 1 < len(args):
                return args[index + 1]
            for option in CONFIG_OPTIONS:
                prefix = option + "="
                if arg.startswith(prefix):
                    return arg[len(prefix):]
    return None


def resolve_config(proc_root="/proc", candidates=DEFAULT_CANDIDATES):
    active = process_config(proc_root)
    if active:
        active = os.path.abspath(active)
        if not os.path.isfile(active):
            raise RuntimeError("Moonraker's configured file does not exist: %s" % active)
        return active

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise RuntimeError("No Moonraker config found in the running process or known K3 data paths")


def main():
    try:
        print(resolve_config())
    except (OSError, RuntimeError) as error:
        print("Moonraker config lookup failed: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
