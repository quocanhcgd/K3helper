#!/usr/bin/env python3
"""Safely add or remove Moonraker's Spoolman section."""

import argparse
import os
import re
import sys
import tempfile


def update_config(path, action, server=None):
    with open(path, "r", encoding="utf-8", newline="") as source:
        content = source.read()

    newline = "\r\n" if "\r\n" in content else "\n"
    normalized = content.replace("\r\n", "\n")
    headers = list(re.finditer(r"(?m)^\[([^\]\r\n]+)\][^\r\n]*(?:\n|$)", normalized))
    sections = [index for index, match in enumerate(headers) if match.group(1).strip() == "spoolman"]
    if len(sections) > 1:
        raise ValueError("moonraker.conf contains multiple [spoolman] sections")

    if sections:
        index = sections[0]
        start = headers[index].start()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(normalized)
        normalized = normalized[:start] + normalized[end:]

    if action == "set":
        block = "[spoolman]\nserver: %s\nsync_rate: 5\n" % server
        normalized = normalized.rstrip() + "\n\n" + block

    output = normalized.replace("\n", newline)
    directory = os.path.dirname(os.path.abspath(path))
    mode = os.stat(path).st_mode & 0o777
    fd, temporary = tempfile.mkstemp(prefix=".moonraker-spoolman-", dir=directory)
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
    parser.add_argument("action", choices=("set", "remove"))
    parser.add_argument("config")
    parser.add_argument("server", nargs="?")
    args = parser.parse_args()
    if args.action == "set" and not args.server:
        parser.error("set requires a Spoolman server URL")
    try:
        update_config(args.config, args.action, args.server)
    except (OSError, ValueError) as error:
        print("Spoolman config update failed: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
