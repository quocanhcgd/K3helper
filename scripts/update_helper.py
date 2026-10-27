#!/usr/bin/env python3
"""Update the K3 Helper Script source without downloading a repository archive."""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath


REPOSITORY = "quocanhcgd/K3helper"
BRANCH = "main"
INSTALL_ROOT = Path("/mnt/UDISK/helper-script")
USER_AGENT = "K3helper-updater/1.0"


def request_bytes(url: str, accept: str = "application/vnd.github+json") -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def runtime_files(tree: list[dict]) -> list[dict]:
    selected = []
    for entry in tree:
        path = entry.get("path", "")
        if entry.get("type") != "blob" or entry.get("mode") not in ("100644", "100755"):
            continue
        if path != "helper.sh" and not path.startswith(("scripts/", "files/")):
            continue
        relative = PurePosixPath(path)
        if relative.is_absolute() or ".." in relative.parts or "__pycache__" in relative.parts:
            continue
        selected.append(entry)
    return sorted(selected, key=lambda entry: (entry["path"] == "helper.sh", entry["path"]))


def git_blob_sha(data: bytes) -> str:
    header = ("blob %d\0" % len(data)).encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def update() -> int:
    root = INSTALL_ROOT.resolve()
    if not root.is_dir():
        raise RuntimeError("Helper Script directory was not found: %s" % root)

    tree_url = "https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (
        REPOSITORY,
        BRANCH,
    )
    tree_data = json.loads(request_bytes(tree_url).decode("utf-8"))
    if tree_data.get("truncated"):
        raise RuntimeError("GitHub returned an incomplete repository file list.")
    files = runtime_files(tree_data.get("tree", []))
    if not any(entry["path"] == "helper.sh" for entry in files):
        raise RuntimeError("GitHub update does not contain helper.sh.")

    stage_root = Path(tempfile.mkdtemp(prefix=".helper-update-", dir=str(root)))
    try:
        staged = []
        for entry in files:
            relative = PurePosixPath(entry["path"])
            destination = (root / Path(*relative.parts)).resolve()
            if root not in destination.parents:
                raise RuntimeError("Unsafe path in update: %s" % entry["path"])

            raw_url = "https://raw.githubusercontent.com/%s/%s/%s" % (
                REPOSITORY,
                BRANCH,
                urllib.parse.quote(entry["path"], safe="/"),
            )
            data = request_bytes(raw_url, "application/octet-stream")
            if git_blob_sha(data) != entry.get("sha"):
                raise RuntimeError("GitHub content checksum failed: %s" % entry["path"])

            stage_path = stage_root / Path(*relative.parts)
            stage_path.parent.mkdir(parents=True, exist_ok=True)
            stage_path.write_bytes(data)
            mode = 0o755 if entry.get("mode") == "100755" else 0o644
            if entry["path"].endswith((".sh", ".py")) or entry["path"] == "helper.sh":
                mode = 0o755
            os.chmod(stage_path, mode)
            staged.append((stage_path, destination))

        for stage_path, destination in staged:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage_path, destination)

        print("Updated %d Helper Script runtime file(s) from %s:%s." % (
            len(staged), REPOSITORY, tree_data.get("sha", BRANCH)
        ))
        print("Existing Fluidd files, printer configuration, and local data were left in place.")
        print("Restart helper.sh to load the updated menu and commands.")
        return 0
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def main() -> int:
    try:
        return update()
    except Exception as exc:
        print("Helper Script update failed: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
