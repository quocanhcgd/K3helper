#!/usr/bin/env python3
"""Install and patch a UDISK-hosted Fluidd copy for the K3 Moonraker API."""

import argparse
import json
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
OLD_FILE_DOWNLOAD = (
    "async downloadFile(e,t){Sm(e,await this.createFileUrlWithToken(e,t))}"
)
NEW_FILE_DOWNLOAD = (
    "async downloadFile(e,t){let n=await this.createFileUrlWithToken(e,t);"
    "try{let r=new URL(n);r.origin!==window.location.origin&&"
    "(r=new URL(r.pathname+r.search,window.location.origin)),n=r.toString()}"
    "catch{}Sm(e,n)}"
)
FIRMWARE_BADGE_ID = "creality-firmware-version-script"
FIRMWARE_BADGE_SCRIPT = "creality-firmware-version.js"
FIRMWARE_INFO_FILE = "creality-firmware-version.json"
CFS_STATUS_ID = "creality-cfs-status-script"
CFS_STATUS_SCRIPT = "creality-cfs-status.js"

FIRMWARE_BADGE_SOURCE = r'''(() => {
  const badgeId = "creality-firmware-version-badge";
  fetch("/creality-firmware-version.json", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error("Firmware version unavailable");
      return response.json();
    })
    .then((info) => {
      if (!info.sys_version) return;
      const showBadge = () => {
        if (!document.body || document.getElementById(badgeId)) return;
        const badge = document.createElement("div");
        badge.id = badgeId;
        badge.textContent = `Creality firmware ${info.sys_version}`;
        badge.title = "Creality system firmware";
        badge.setAttribute("role", "status");
        badge.style.cssText = "position:fixed;left:12px;bottom:12px;z-index:10000;padding:5px 8px;border-radius:4px;background:rgba(32,36,40,.86);color:#fff;font:12px/1.4 sans-serif;pointer-events:none;box-shadow:0 1px 4px rgba(0,0,0,.25)";
        document.body.appendChild(badge);
      };
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", showBadge, { once: true });
      } else {
        showBadge();
      }
    })
    .catch(() => {});
})();
'''

CFS_STATUS_SOURCE = r'''(() => {
  const rootId = "creality-cfs-status-panel";
  if (document.getElementById(rootId)) return;

  const panel = document.createElement("section");
  panel.id = rootId;
  panel.style.cssText = "position:fixed;left:12px;bottom:44px;z-index:10000;width:min(300px,calc(100vw - 24px));color:#f4f5f6;background:rgba(32,36,40,.94);border:1px solid rgba(255,255,255,.18);border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.3);font:12px/1.45 sans-serif";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", "false");
  toggle.style.cssText = "display:flex;align-items:center;gap:8px;width:100%;min-height:32px;padding:6px 9px;border:0;background:transparent;color:inherit;text-align:left;font:600 12px/1.4 sans-serif;cursor:pointer";
  const dot = document.createElement("span");
  dot.style.cssText = "width:8px;height:8px;flex:none;border-radius:50%;background:#8b9298";
  const summary = document.createElement("span");
  summary.textContent = "CFS: checking";
  toggle.append(dot, summary);

  const details = document.createElement("div");
  details.hidden = true;
  details.style.cssText = "padding:0 9px 8px;border-top:1px solid rgba(255,255,255,.14)";
  toggle.addEventListener("click", () => {
    details.hidden = !details.hidden;
    toggle.setAttribute("aria-expanded", String(!details.hidden));
  });
  panel.append(toggle, details);

  const setState = (text, color, lines) => {
    summary.textContent = text;
    dot.style.background = color;
    details.replaceChildren();
    for (const item of lines) {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;gap:6px;padding-top:5px;overflow-wrap:anywhere";
      if (item.color) {
        const swatch = document.createElement("span");
        swatch.setAttribute("aria-label", "Filament color #" + item.color);
        swatch.style.cssText = "width:12px;height:12px;flex:none;border:1px solid rgba(255,255,255,.55);border-radius:2px;background:#" + item.color;
        row.appendChild(swatch);
      }
      const label = document.createElement("span");
      label.textContent = item.text;
      row.appendChild(label);
      details.appendChild(row);
    }
  };

  const displayCode = value => {
    if (value === undefined || value === null || value === "" || value === "-1") return "";
    return String(value);
  };

  const refresh = async () => {
    try {
      const response = await fetch("/printer/objects/query?box", { cache: "no-store" });
      if (!response.ok) throw new Error("Moonraker API " + response.status);
      const payload = await response.json();
      const box = payload?.result?.status?.box;
      if (!box) throw new Error("CFS status unavailable");

      const units = Object.keys(box).filter(key => /^T[1-4]$/.test(key) && box[key] && typeof box[key] === "object");
      const online = box.is_online === true || box.state === "connect";
      const lines = [];
      let loaded = 0;
      for (const unitName of units) {
        const unit = box[unitName];
        lines.push({ text: unitName + " · " + (unit.type || "CFS") });
        const types = Array.isArray(unit.material_type) ? unit.material_type : [];
        const colors = Array.isArray(unit.color_value) ? unit.color_value : [];
        const remaining = Array.isArray(unit.remain_len) ? unit.remain_len : [];
        for (let index = 0; index < Math.max(types.length, colors.length); index++) {
          const slot = unitName + String.fromCharCode(65 + index);
          const materialCode = displayCode(types[index]);
          const colorCode = displayCode(colors[index]);
          const match = Array.isArray(box.same_material) && box.same_material.find(item =>
            Array.isArray(item) && Array.isArray(item[2]) && item[2].includes(slot)
          );
          const materialName = match && typeof match[3] === "string" ? match[3] : materialCode;
          const isEmpty = !materialCode && !colorCode;
          const remainder = remaining[index] && remaining[index] !== "-1" ? " · " + remaining[index] + " mm" : "";
          lines.push({
            text: slot + ": " + (isEmpty ? "empty" : (materialName || "material") + remainder),
            color: colorCode ? colorCode.slice(-6) : "",
          });
          if (!isEmpty) loaded++;
        }
      }

      if (!units.length) {
        const rack = box.filament === 1 ? " · external spool detected" : "";
        setState(online ? "CFS: online" : "CFS: unavailable", online ? "#39b86b" : "#e0a23c", [{ text: "No CFS unit details reported" + rack }]);
        return;
      }

      setState("CFS: " + (online ? "online" : "offline") + " · " + loaded + " slot(s)", online ? "#39b86b" : "#d85c5c", lines);
    } catch (error) {
      setState("CFS: unavailable", "#e0a23c", [{ text: "Moonraker did not return the Klipper box status" }]);
    }
  };

  const mount = () => {
    if (!document.body || document.getElementById(rootId)) return;
    document.body.appendChild(panel);
    refresh();
    window.setInterval(refresh, 10000);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, { once: true });
  else mount();
})();
'''


def install_firmware_version_display(root: Path, version_file: Path) -> None:
    if not version_file.is_file():
        raise RuntimeError(f"Creality firmware version file does not exist: {version_file}")

    try:
        source = json.loads(version_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read Creality firmware version JSON: {exc}") from exc

    version = source.get("sys_version") if isinstance(source, dict) else None
    if not isinstance(version, (str, int, float)) or not str(version).strip():
        raise RuntimeError("Firmware version JSON does not contain a usable sys_version value.")

    info = {"sys_version": str(version).strip()}
    (root / FIRMWARE_INFO_FILE).write_text(
        json.dumps(info, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    (root / FIRMWARE_BADGE_SCRIPT).write_text(FIRMWARE_BADGE_SOURCE, encoding="utf-8")

    index = root / "index.html"
    html = index.read_text(encoding="utf-8")
    if FIRMWARE_BADGE_ID not in html:
        script_tag = f'<script id="{FIRMWARE_BADGE_ID}" defer src="/{FIRMWARE_BADGE_SCRIPT}"></script>'
        if re.search(r"</body\s*>", html, re.IGNORECASE):
            html = re.sub(r"</body\s*>", script_tag + "</body>", html, count=1, flags=re.IGNORECASE)
        elif re.search(r"</html\s*>", html, re.IGNORECASE):
            html = re.sub(r"</html\s*>", script_tag + "</html>", html, count=1, flags=re.IGNORECASE)
        else:
            raise RuntimeError("Fluidd index.html has no body or html closing tag for firmware badge injection.")
        index.write_text(html, encoding="utf-8")


def install_cfs_status_display(root: Path) -> None:
    (root / CFS_STATUS_SCRIPT).write_text(CFS_STATUS_SOURCE, encoding="utf-8")
    index = root / "index.html"
    html = index.read_text(encoding="utf-8")
    if CFS_STATUS_ID not in html:
        script_tag = f'<script id="{CFS_STATUS_ID}" defer src="/{CFS_STATUS_SCRIPT}"></script>'
        if re.search(r"</body\s*>", html, re.IGNORECASE):
            html = re.sub(r"</body\s*>", script_tag + "</body>", html, count=1, flags=re.IGNORECASE)
        elif re.search(r"</html\s*>", html, re.IGNORECASE):
            html = re.sub(r"</html\s*>", script_tag + "</html>", html, count=1, flags=re.IGNORECASE)
        else:
            raise RuntimeError("Fluidd index.html has no body or html closing tag for CFS status injection.")
        index.write_text(html, encoding="utf-8")


def patch_bundle(root: Path) -> None:
    list_matches = []
    delete_matches = []
    download_matches = []
    for asset in (root / "assets").glob("*.js"):
        text = asset.read_text(encoding="utf-8")
        if "setWebcamsList(" in text:
            list_matches.append((asset, text))
        if "serverWebcamsDelete(" in text and "server.webcams.delete_item" in text:
            delete_matches.append((asset, text))
        if "async downloadFile(" in text and "createFileUrlWithToken" in text:
            download_matches.append((asset, text))

    if not list_matches or not delete_matches:
        raise RuntimeError(
            "Expected Fluidd webcam-list and delete API modules; "
            f"found {len(list_matches)} and {len(delete_matches)}."
        )

    for list_asset, list_text in list_matches:
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
                raise RuntimeError(f"Fluidd webcam-list code did not match a supported version: {list_asset.name}")
        list_asset.write_text(list_text, encoding="utf-8")

    for delete_asset, _ in delete_matches:
        delete_text = delete_asset.read_text(encoding="utf-8")
        if OLD_WEBCAM_DELETE in delete_text:
            delete_text = delete_text.replace(OLD_WEBCAM_DELETE, NEW_WEBCAM_DELETE)
        else:
            start = delete_text.find("serverWebcamsDelete(")
            end = delete_text.find("serverSensorsList", start)
            if start < 0 or end < 0:
                raise RuntimeError(f"Fluidd webcam-delete code did not match a supported version: {delete_asset.name}")
            segment = delete_text[start:end]
            segment, count = re.subn(r"params:\{uid:(\w+)\}", r"params:{name:\1}", segment, count=1)
            if count != 1 and "params:{name:" not in segment:
                raise RuntimeError(f"Fluidd delete call has an unsupported parameter format: {delete_asset.name}")
            delete_text = delete_text[:start] + segment + delete_text[end:]
        delete_asset.write_text(delete_text, encoding="utf-8")

    if not download_matches:
        raise RuntimeError("Could not find Fluidd file-download module.")

    for download_asset, _ in download_matches:
        download_text = download_asset.read_text(encoding="utf-8")
        if OLD_FILE_DOWNLOAD in download_text:
            download_text = download_text.replace(OLD_FILE_DOWNLOAD, NEW_FILE_DOWNLOAD)
        elif NEW_FILE_DOWNLOAD not in download_text:
            pattern = re.compile(
                r"async downloadFile\((\w+),(\w+)\)\{"
                r"Sm\(\1,await this\.createFileUrlWithToken\(\1,\2\)\)\}"
            )
            download_text, count = pattern.subn(NEW_FILE_DOWNLOAD, download_text, count=1)
            if count != 1:
                raise RuntimeError(
                    f"Fluidd file-download code did not match a supported version: {download_asset.name}"
                )
        download_asset.write_text(download_text, encoding="utf-8")


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


def install(
    source: Path,
    destination: Path,
    nginx: Path,
    version_file: Path,
    refresh: bool = False,
) -> None:
    if not source.is_dir():
        raise RuntimeError(f"Fluidd source directory does not exist: {source}")

    if refresh:
        if source.resolve() == destination.resolve():
            raise RuntimeError("Cannot refresh Fluidd when source and destination are the same directory.")
        staging = destination.with_name(destination.name + ".refresh")
        previous = destination.with_name(destination.name + ".previous")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(previous, ignore_errors=True)
        shutil.copytree(source, staging)
        if not (staging / "index.html").is_file():
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError(f"Fluidd index.html is missing from {source}")
        patch_bundle(staging)
        if destination.exists():
            destination.rename(previous)
        try:
            staging.rename(destination)
        except Exception:
            if previous.exists() and not destination.exists():
                previous.rename(destination)
            raise
        shutil.rmtree(previous, ignore_errors=True)
    elif not destination.exists():
        shutil.copytree(source, destination)
    if not (destination / "index.html").is_file():
        raise RuntimeError(f"Fluidd index.html is missing from {destination}")

    if not refresh:
        patch_bundle(destination)
    install_firmware_version_display(destination, version_file)
    install_cfs_status_display(destination)
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
    parser.add_argument(
        "--firmware-version",
        type=Path,
        default=Path("/mnt/UDISK/creality/userdata/config/system_version.json"),
    )
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        install(args.source, args.destination, args.nginx, args.firmware_version, args.refresh)
    except Exception as exc:
        print(f"K3 Fluidd compatibility setup failed: {exc}", file=sys.stderr)
        return 1
    print("Fluidd patched for K3 webcam compatibility and Creality firmware version display.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
