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
PERSISTENT_CONFIG_DIRS = (
    "/mnt/SDCARD/cxsw/printer_data/config",
    "/mnt/UDISK/printer_data/config",
)
STOCK_CONFIG = "/usr/share/moonraker/moonraker.conf"
CONFIG_OPTIONS = ("-c", "--configfile", "--config-file")
CONFIG_ENV_NAMES = ("MOONRAKER_CONFIG", "MOONRAKER_CONFIG_FILE", "CONFIG_FILE", "CONF")


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
        for arg in args:
            if arg.endswith(".conf") and (arg == STOCK_CONFIG or "moonraker" in os.path.basename(arg).lower()):
                return arg
        try:
            with open(os.path.join(os.path.dirname(cmdline), "environ"), "rb") as source:
                environment = source.read().split(b"\0")
        except OSError:
            environment = []
        for item in environment:
            text = item.decode("utf-8", "replace")
            name, separator, value = text.partition("=")
            if separator and name in CONFIG_ENV_NAMES and value.endswith(".conf"):
                return value
        for descriptor in glob.glob(os.path.join(os.path.dirname(cmdline), "fd", "*")):
            try:
                target = os.path.realpath(descriptor)
            except OSError:
                continue
            if target.endswith("moonraker.conf"):
                return target
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
    if os.path.isfile(STOCK_CONFIG):
        return STOCK_CONFIG
    raise RuntimeError("No Moonraker config found in the running process or known K3 data paths")


def persistent_wrapper_path(candidates=DEFAULT_CANDIDATES, directories=PERSISTENT_CONFIG_DIRS):
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8", errors="replace") as source:
                if "[include %s]" % STOCK_CONFIG in source.read():
                    return candidate
        except OSError:
            continue
    for directory in directories:
        if os.path.isdir(directory) and os.access(directory, os.W_OK):
            return os.path.join(directory, "moonraker.conf")
    raise RuntimeError("No writable Moonraker config directory found on UDISK mounts")


def main():
    try:
        if len(sys.argv) == 2 and sys.argv[1] == "wrapper":
            print(persistent_wrapper_path())
        elif len(sys.argv) == 1:
            print(resolve_config())
        else:
            print("Usage: %s [wrapper]" % sys.argv[0], file=sys.stderr)
            return 2
    except (OSError, RuntimeError) as error:
        print("Moonraker config lookup failed: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
