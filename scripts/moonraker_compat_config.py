#!/usr/bin/env python3
"""Manage the K3 Moonraker compatibility component configuration."""

import argparse
import os
import re
import tempfile


SECTION_NAME = "k3helper_compat"
MARKER = "# K3 Helper Script: Fluidd compatibility endpoints"
SECTION = MARKER + "\n[k3helper_compat]\n"


def update_config(path, action):
    if action not in ("install", "remove"):
        raise ValueError("action must be install or remove")
    with open(path, "r", encoding="utf-8", newline="") as source:
        content = source.read()
    newline = "\r\n" if "\r\n" in content else "\n"
    normalized = content.replace("\r\n", "\n")
    headers = list(re.finditer(r"(?m)^\[([^\]\r\n]+)\][^\r\n]*(?:\n|$)", normalized))
    matches = [i for i, match in enumerate(headers) if match.group(1).strip() == SECTION_NAME]
    if len(matches) > 1:
        raise ValueError("Moonraker config contains multiple [%s] sections" % SECTION_NAME)

    if matches:
        index = matches[0]
        start = headers[index].start()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(normalized)
        block_start = normalized.rfind(MARKER + "\n", 0, start)
        if block_start < 0 or normalized[block_start:start].strip() != MARKER:
            raise ValueError("An unmanaged [%s] section already exists" % SECTION_NAME)
        normalized = normalized[:block_start] + normalized[end:]

    if action == "install":
        normalized = normalized.rstrip() + "\n\n" + SECTION
    else:
        normalized = normalized.rstrip("\n") + "\n"
    output = normalized.replace("\n", newline)
    directory = os.path.dirname(os.path.abspath(path))
    mode = os.stat(path).st_mode & 0o777
    fd, temporary = tempfile.mkstemp(prefix=".moonraker-compat-", dir=directory)
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
        print("Moonraker compatibility config failed: %s" % error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
