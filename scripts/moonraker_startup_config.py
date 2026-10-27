#!/usr/bin/env python3
"""Patch or restore the K3 Moonraker init script's config path."""

import os
import glob
import re
import shutil
import sys
import tempfile


STOCK_CONFIG = "/usr/share/moonraker/moonraker.conf"
HELPER_PYTHONPATH = "/mnt/UDISK/helper-script/scripts"
PYTHONPATH_LINE = "export PYTHONPATH=%s${PYTHONPATH:+:$PYTHONPATH}" % HELPER_PYTHONPATH
SERVICE_CANDIDATES = (
    "/etc/init.d/moonraker",
    "/etc/init.d/S56moonraker",
    "/etc/rc.d/S56moonraker",
)


def inject_pythonpath(content):
    """Add PYTHONPATH without moving a shell script's required shebang."""
    if PYTHONPATH_LINE in content:
        return content
    line_end = "\r\n" if "\r\n" in content else "\n"
    if content.startswith("#!"):
        first_end = content.find("\n")
        if first_end >= 0:
            return content[: first_end + 1] + PYTHONPATH_LINE + line_end + content[first_end + 1 :]
    return PYTHONPATH_LINE + line_end + content


def service_paths(candidates=None):
    if candidates is None:
        candidates = list(SERVICE_CANDIDATES)
        for directory in ("/etc/init.d", "/etc/rc.d"):
            candidates.extend(sorted(glob.glob(os.path.join(directory, "*moonraker*"))))
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
        if STOCK_CONFIG in content or ("moonraker" in content.lower() and re.search(r"(?m)^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=", content)):
            return path, content
    raise RuntimeError("No Moonraker init script references %s" % STOCK_CONFIG)


def find_services(candidates=None):
    found = []
    for path in service_paths(candidates):
        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as source:
                content = source.read()
        except OSError:
            continue
        if STOCK_CONFIG in content or ("moonraker" in content.lower() and re.search(r"(?m)^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=", content)):
            found.append((path, content))
    if not found:
        raise RuntimeError("No Moonraker init script references %s" % STOCK_CONFIG)
    return found


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
    updated = re.sub(
        r"(?P<prefix>(?:-c|--config(?:file|-file))\s+)(?:['\"])?%s(?:['\"])?" % re.escape(STOCK_CONFIG),
        lambda match: match.group("prefix") + config_path,
        updated,
    )
    config_changed = updated != content
    if not config_changed:
        # Some Creality init variants store the path in a differently named
        # variable while retaining the .conf suffix.
        updated = re.sub(
            r"(?m)^(\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*['\"]?)[^'\"\r\n]*moonraker\.conf(['\"]?\s*)$",
            lambda match: match.group(1) + config_path + match.group(2),
            content,
            count=1,
        )
    updated = inject_pythonpath(updated)
    if updated == content:
        raise RuntimeError("Moonraker startup config path was not changed")
    atomic_write(path, updated, os.stat(path).st_mode & 0o777)
    return path


def patch_all(config_path, candidates=None):
    patched = []
    for path, content in find_services(candidates):
        backup = path + ".k3helper-spoolman.bak"
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        updated = content.replace(STOCK_CONFIG, config_path)
        updated = re.sub(
            r"(?P<prefix>(?:-c|--config(?:file|-file))\s+)(?:['\"])?%s(?:['\"])?" % re.escape(STOCK_CONFIG),
            lambda match: match.group("prefix") + config_path,
            updated,
        )
        config_changed = updated != content
        if not config_changed:
            updated = re.sub(
                r"(?m)^(\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*['\"]?)[^'\"\r\n]*moonraker\.conf(['\"]?\s*)$",
                lambda match: match.group(1) + config_path + match.group(2),
                content,
                count=1,
            )
        updated = inject_pythonpath(updated)
        if updated == content:
            raise RuntimeError("Moonraker startup config path was not changed in %s" % path)
        atomic_write(path, updated, os.stat(path).st_mode & 0o777)
        patched.append(path)
    return patched


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


def restore_all(candidates=None):
    restored = []
    for path in service_paths(candidates):
        backup = path + ".k3helper-spoolman.bak"
        if not os.path.isfile(backup):
            continue
        with open(backup, "r", encoding="utf-8", errors="replace", newline="") as source:
            original = source.read()
        atomic_write(path, original, os.stat(path).st_mode & 0o777)
        os.unlink(backup)
        restored.append(path)
    if not restored:
        raise RuntimeError("No saved Moonraker init script backup was found")
    return restored


def patch_pythonpath(candidates=None):
    """Enable the K3 Helper Python hooks without changing Moonraker's config."""
    patched = []
    for path, content in find_services(candidates):
        backup = path + ".k3helper-pythonpath.bak"
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        updated = inject_pythonpath(content)
        if updated == content:
            patched.append(path)
            continue
        atomic_write(path, updated, os.stat(path).st_mode & 0o777)
        patched.append(path)
    if not patched:
        raise RuntimeError("No Moonraker init script could be patched")
    return patched


def main():
    try:
        if len(sys.argv) == 2 and sys.argv[1] == "check":
            path, _ = find_service()
            print(path)
        elif len(sys.argv) == 3 and sys.argv[1] == "patch":
            print("\n".join(patch_all(sys.argv[2])))
        elif len(sys.argv) == 2 and sys.argv[1] == "restore":
            print("\n".join(restore_all()))
        elif len(sys.argv) == 2 and sys.argv[1] == "patch-pythonpath":
            print("\n".join(patch_pythonpath()))
        else:
            print("Usage: %s [check|patch CONFIG|restore]" % sys.argv[0], file=sys.stderr)
            return 2
    except (OSError, RuntimeError) as error:
        print("Moonraker startup config update failed: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
