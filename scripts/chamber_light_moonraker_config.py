#!/usr/bin/env python3
"""Manage the Moonraker section for the K3 chamber-light WebSocket bridge."""

import argparse
import os
import re
import sys
import tempfile


SECTION_NAME = "chamber_light_ws"
MARKER = "# K3 Helper Script: chamber light WebSocket bridge"
SECTION = MARKER + "\n[chamber_light_ws]\nhost: 127.0.0.1\nport: 9999\n"


def update_config(path, action):
    if action not in ("install", "remove"):
        raise ValueError("action must be install or remove")
    with open(path, "r", encoding="utf-8", newline="") as source:
        content = source.read()
    newline = "\r\n" if "\r\n" in content else "\n"
    normalized = content.replace("\r\n", "\n")
    headers = list(re.finditer(r"(?m)^\[([^\]\r\n]+)\][^\r\n]*(?:\n|$)", normalized))
    matches = [index for index, match in enumerate(headers) if match.group(1).strip() == SECTION_NAME]
    if len(matches) > 1:
        raise ValueError("Moonraker config contains multiple [%s] sections" % SECTION_NAME)

    owned = False
    if matches:
        index = matches[0]
        start = headers[index].start()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(normalized)
        block_start = normalized.rfind(MARKER + "\n", 0, start)
        if block_start >= 0 and normalized[block_start:start].strip() == MARKER:
            start = block_start
            owned = True
        if not owned:
            raise ValueError("An unmanaged [%s] section already exists" % SECTION_NAME)
        normalized = normalized[:start] + normalized[end:]

    if action == "install":
        normalized = normalized.rstrip() + "\n\n" + SECTION
    else:
        normalized = normalized.rstrip("\n") + "\n"
    output = normalized.replace("\n", newline)
    directory = os.path.dirname(os.path.abspath(path))
    mode = os.stat(path).st_mode & 0o777
    fd, temporary = tempfile.mkstemp(prefix=".chamber-light-moonraker-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            target.write(output)
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "remove"))
    parser.add_argument("config")
    args = parser.parse_args()
    try:
        update_config(args.config, args.action)
    except (OSError, ValueError) as error:
        print("Chamber-light Moonraker config failed: %s" % error, file=sys.stderr)
        return 1
    print("Moonraker chamber-light section updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
