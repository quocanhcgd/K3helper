#!/usr/bin/env python3
"""Install and patch a UDISK-hosted Fluidd copy for the K3 Moonraker API."""

import argparse
import re
import shutil
import sys
from pathlib import Path


OLD_WEBCAM_LIST = "setWebcamsList(r,e){r.webcams=e.webcams||[]}"
OLD_K3_WEBCAM_LIST = (
    "setWebcamsList(r,e){r.webcams=(e.webcams||[]).map(c=>"
    "({...c,uid:c.uid??c.name,enabled:c.enabled??!0}))}"
)
NEW_WEBCAM_LIST = (
    "setWebcamsList(r,e){r.webcams=(e.webcams||[]).map(c=>"
    "({...c,uid:c.uid??c.name,enabled:(c.name===\"K3 Camera\"||"
    "c.service===\"webrtc-go2rtc\")?!0:(c.enabled??!0)}))}"
)
OLD_WEBCAM_DELETE = (
    'serverWebcamsDelete(r){ue("server.webcams.delete_item",{params:{uid:r}})}'
)
NEW_WEBCAM_DELETE = (
    'serverWebcamsDelete(r){ue("server.webcams.delete_item",{params:{name:r}})}'
)


def patch_bundle(root: Path) -> None:
    list_matches = []
    delete_matches = []
    for asset in (root / "assets").glob("*.js"):
        text = asset.read_text(encoding="utf-8")
        if "setWebcamsList(" in text:
            list_matches.append((asset, text))
        if "serverWebcamsDelete(" in text and "server.webcams.delete_item" in text:
            delete_matches.append((asset, text))

    if len(list_matches) != 1 or len(delete_matches) != 1:
        raise RuntimeError(
            "Expected one Fluidd webcam-list module and one delete API module; "
            f"found {len(list_matches)} and {len(delete_matches)}."
        )

    list_asset, list_text = list_matches[0]
    if OLD_WEBCAM_LIST in list_text:
        list_text = list_text.replace(OLD_WEBCAM_LIST, NEW_WEBCAM_LIST)
    elif OLD_K3_WEBCAM_LIST in list_text:
        list_text = list_text.replace(OLD_K3_WEBCAM_LIST, NEW_WEBCAM_LIST)
    elif "c.name===\"K3 Camera\"||c.service===\"webrtc-go2rtc\"" not in list_text:
        pattern = re.compile(r"setWebcamsList\((\w+),(\w+)\)\{\1\.webcams=\2\.webcams\|\|\[\]\}")
        list_text, count = pattern.subn(
            lambda match: (
                f"setWebcamsList({match.group(1)},{match.group(2)})"
                f"{{{match.group(1)}.webcams=({match.group(2)}.webcams||[]).map(c=>"
                "({...c,uid:c.uid??c.name,enabled:(c.name===\"K3 Camera\"||"
                "c.service===\"webrtc-go2rtc\")?!0:(c.enabled??!0)}))}"
            ),
            list_text,
            count=1,
        )
        if count != 1:
            raise RuntimeError("Fluidd webcam-list code did not match a supported version.")
    list_asset.write_text(list_text, encoding="utf-8")

    delete_asset, delete_text = delete_matches[0]
    if delete_asset == list_asset:
        delete_text = list_text
    if OLD_WEBCAM_DELETE in delete_text:
        delete_text = delete_text.replace(OLD_WEBCAM_DELETE, NEW_WEBCAM_DELETE)
    else:
        start = delete_text.find("serverWebcamsDelete(")
        end = delete_text.find("serverSensorsList", start)
        if start < 0 or end < 0:
            raise RuntimeError("Fluidd webcam-delete code did not match a supported version.")
        segment = delete_text[start:end]
        segment, count = re.subn(r"params:\{uid:(\w+)\}", r"params:{name:\1}", segment, count=1)
        if count != 1 and "params:{name:" not in segment:
            raise RuntimeError("Fluidd delete call has an unsupported parameter format.")
        delete_text = delete_text[:start] + segment + delete_text[end:]
    delete_asset.write_text(delete_text, encoding="utf-8")


def server_blocks(config: str):
    for match in re.finditer(r"\bserver\s*\{", config):
        start = match.start()
        line_start = config.rfind("\n", 0, start) + 1
        if config[line_start:start].lstrip().startswith("#"):
            continue
        brace = config.find("{", match.start())
        depth = 0
        quote = None
        escaped = False
        for pos in range(brace, len(config)):
            char = config[pos]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in "\"'":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield start, pos + 1
                    break


def configure_nginx(path: Path, document_root: Path, state_path: Path) -> None:
    config = path.read_text(encoding="utf-8")
    root_value = str(document_root)
    edits = []
    original_roots = []
    found_fluidd_server = False

    for start, end in server_blocks(config):
        block = config[start:end]
        if not re.search(r"\blisten\s+4408\b", block):
            continue
        found_fluidd_server = True
        roots = list(re.finditer(r"(?m)^(\s*root\s+)([^;]+)(;)", block))
        if len(roots) != 1:
            raise RuntimeError("Expected one root directive in the Fluidd server block.")
        current = roots[0].group(2).strip()
        if current != root_value:
            original_roots.append(current)
            updated = roots[0].group(1) + root_value + roots[0].group(3)
            block = block[: roots[0].start()] + updated + block[roots[0].end() :]
            edits.append((start, end, block))

    if not found_fluidd_server:
        raise RuntimeError("Could not find the Fluidd server block listening on port 4408.")

    if len(original_roots) > 1:
        raise RuntimeError("Found more than one Fluidd root directive to replace.")
    if edits:
        start, end, block = edits[0]
        if not state_path.exists():
            state_path.write_text(original_roots[0] + "\n", encoding="utf-8")
            shutil.copy2(path, state_path.with_suffix(".nginx.conf.bak"))
        config = config[:start] + block + config[end:]
        path.write_text(config, encoding="utf-8")


def install(source: Path, destination: Path, nginx: Path) -> None:
    if not destination.exists():
        if not source.is_dir():
            raise RuntimeError(f"Fluidd source directory does not exist: {source}")
        shutil.copytree(source, destination)
    if not (destination / "index.html").is_file():
        raise RuntimeError(f"Fluidd index.html is missing from {destination}")

    patch_bundle(destination)
    configure_nginx(
        nginx,
        destination,
        destination.parent / ".k3_fluidd_original_root",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("install", choices=["install"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--nginx", type=Path, required=True)
    args = parser.parse_args()
    try:
        install(args.source, args.destination, args.nginx)
    except Exception as exc:
        print(f"K3 Fluidd compatibility setup failed: {exc}", file=sys.stderr)
        return 1
    print("Fluidd patched for K3 webcam compatibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
