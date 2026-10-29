#!/usr/bin/env python3
"""Manage the K3 chamber-light toggle macro shown in Fluidd's Macros card."""

import argparse
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


INCLUDE_MARKER = "# K3 Helper Script: chamber light macro"
INCLUDE_LINE = "[include chamber_light.cfg]"
MACRO_MARKER = "# K3HELPER_CHAMBER_LIGHT_V1"
PIN_CONFIG = '''[output_pin chamber_led]
pin: rpi:gpio42
value: 0
shutdown_value: 0
'''
MACROS_CONFIG = '''[gcode_macro CHAMBER_LED_ON]
gcode:
  SET_PIN PIN=chamber_led VALUE=1

[gcode_macro CHAMBER_LED_OFF]
gcode:
  SET_PIN PIN=chamber_led VALUE=0
'''


def moonraker_objects() -> set[str]:
    request = urllib.request.Request(
        "http://127.0.0.1:7125/printer/objects/list",
        headers={"User-Agent": "K3-Helper-Script"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        import json

        payload = json.load(response)
    objects = payload.get("result", {}).get("objects", [])
    if not isinstance(objects, list):
        raise RuntimeError("Moonraker returned an invalid Klipper object list.")
    return set(objects)


def atomic_write(path: Path, content: str, mode: int) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".k3helper-chamber-light-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            target.write(content)
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


def backup_config(path: Path) -> Path:
    backup = path.with_name(path.name + ".k3helper-chamber-light.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def manage_config(path: Path, action: str, objects: Optional[set[str]] = None) -> bool:
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(f"Klipper config was not found: {path}")
    macro_path = path.parent / "chamber_light.cfg"
    with path.open("r", encoding="utf-8", newline="") as source:
        text = source.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    normalized = text.replace("\r\n", "\n")
    managed_include = INCLUDE_MARKER + "\n" + INCLUDE_LINE
    already_included = managed_include in normalized
    macro_is_owned = macro_path.is_file() and MACRO_MARKER in macro_path.read_text(encoding="utf-8")

    if action == "install":
        if already_included and macro_is_owned:
            return False
        if INCLUDE_LINE in normalized or macro_path.exists():
            raise RuntimeError("chamber_light.cfg or its include already exists and is not Helper Script-owned.")
        objects = moonraker_objects() if objects is None else objects
        if "gcode_macro CHAMBER_LED_ON" in objects or "gcode_macro CHAMBER_LED_OFF" in objects:
            raise RuntimeError("A CHAMBER_LED_ON or CHAMBER_LED_OFF macro already exists; left existing macros unchanged.")
        backup_config(path)
        config = MACRO_MARKER + "\n"
        if "output_pin chamber_led" not in objects:
            config += PIN_CONFIG + "\n"
        config += MACROS_CONFIG
        macro_path.write_text(config.replace("\n", newline), encoding="utf-8", newline="")
        save_config = re.search(r"(?m)^#\*# <[- ]*SAVE_CONFIG[- ]*>[^\n]*(?:\n|$)", normalized)
        if save_config:
            insertion = save_config.start()
            prefix = normalized[:insertion]
            suffix = "" if not prefix or prefix.endswith("\n") else "\n"
            normalized = prefix + suffix + managed_include + "\n\n" + normalized[insertion:]
        else:
            suffix = "" if not normalized or normalized.endswith("\n") else "\n"
            normalized += suffix + managed_include + "\n"
        try:
            atomic_write(path, normalized.replace("\n", newline), path.stat().st_mode & 0o777)
        except Exception:
            macro_path.unlink(missing_ok=True)
            raise
        return True

    if action == "remove":
        if not already_included and not macro_is_owned:
            return False
        if already_included != macro_is_owned:
            raise RuntimeError("Managed include and macro file do not match; left both unchanged.")
        backup_config(path)
        normalized = normalized.replace(managed_include + "\n", "", 1)
        normalized = normalized.replace(managed_include, "", 1)
        atomic_write(path, normalized.replace("\n", newline), path.stat().st_mode & 0o777)
        macro_path.unlink()
        return True

    raise ValueError("action must be install or remove")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "remove"))
    parser.add_argument("printer_config", type=Path)
    args = parser.parse_args()
    try:
        changed = manage_config(args.printer_config, args.action)
    except (OSError, RuntimeError, urllib.error.URLError, ValueError) as error:
        print(f"Chamber light setup failed: {error}", file=sys.stderr)
        return 1
    print("Configuration updated." if changed else "Configuration already in requested state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
