#!/usr/bin/env python3
"""Patch or restore the K3 Moonraker init script's config path."""

import os
import shutil
import sys
import tempfile


STOCK_CONFIG = "/usr/share/moonraker/moonraker.conf"
SERVICE_CANDIDATES = (
    "/etc/init.d/moonraker",
    "/etc/init.d/S56moonraker",
    "/etc/rc.d/S56moonraker",
)


def service_paths(candidates=None):
    candidates = SERVICE_CANDIDATES if candidates is None else candidates
    seen = set()
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        path = os.path.realpath(candidate)
        if path not in seen:
            seen.add(path)
            yield path


def find_service(candidates=None):
    for path in service_paths(candidates):
        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as source:
                content = source.read()
        except OSError:
            continue
        if STOCK_CONFIG in content:
            return path, content
    raise RuntimeError("No Moonraker init script references %s" % STOCK_CONFIG)


def atomic_write(path, data, mode):
    directory = os.path.dirname(path)
    fd, temporary = tempfile.mkstemp(prefix=".moonraker-config-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def patch(config_path, candidates=None):
    path, content = find_service(candidates)
    backup = path + ".k3helper-spoolman.bak"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    updated = content.replace(STOCK_CONFIG, config_path)
    if updated == content:
        raise RuntimeError("Moonraker startup config path was not changed")
    atomic_write(path, updated, os.stat(path).st_mode & 0o777)
    return path


def restore(candidates=None):
    for path in service_paths(candidates):
        backup = path + ".k3helper-spoolman.bak"
        if not os.path.isfile(backup):
            continue
        with open(backup, "r", encoding="utf-8", errors="replace", newline="") as source:
            original = source.read()
        atomic_write(path, original, os.stat(path).st_mode & 0o777)
        os.unlink(backup)
        return path
    raise RuntimeError("No saved Moonraker init script backup was found")


def main():
    try:
        if len(sys.argv) == 2 and sys.argv[1] == "check":
            path, _ = find_service()
            print(path)
        elif len(sys.argv) == 3 and sys.argv[1] == "patch":
            print(patch(sys.argv[2]))
        elif len(sys.argv) == 2 and sys.argv[1] == "restore":
            print(restore())
        else:
            print("Usage: %s [check|patch CONFIG|restore]" % sys.argv[0], file=sys.stderr)
            return 2
    except (OSError, RuntimeError) as error:
        print("Moonraker startup config update failed: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
