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
    "async downloadFile(e,t){let n=this.createFileUrl(e,t);"
    "try{let r=new URL(n);r.origin!==window.location.origin&&"
    "(r=new URL(r.pathname+r.search,window.location.origin)),n=r.toString();"
    "let a=await fetch(n,{credentials:\"same-origin\"});if(!a.ok)throw Error(\"Download failed: \"+a.status);"
    "let o=URL.createObjectURL(await a.blob()),s=document.createElement(\"a\");"
    "s.href=o;s.download=e;document.body.appendChild(s);s.click();s.remove();"
    "setTimeout(()=>URL.revokeObjectURL(o),1000)}catch{}}"
)
LEGACY_FILE_DOWNLOAD = (
    "async downloadFile(e,t){let n=this.createFileUrl(e,t);"
    "try{let r=new URL(n);r.origin!==window.location.origin&&"
    "(r=new URL(r.pathname+r.search,window.location.origin)),n=r.toString();"
    "window.location.assign(n)}catch{}}"
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
  panel.style.cssText = "grid-column:1/-1;width:100%;max-height:min(560px,70vh);overflow:auto;color:#f4f5f6;background:#202428;border:1px solid rgba(255,255,255,.18);border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.2);font:13px/1.45 sans-serif;margin:12px 0";

  const header = document.createElement("div");
  header.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.14)";
  const title = document.createElement("div");
  title.style.cssText = "display:flex;align-items:center;gap:8px;font-weight:700";
  const dot = document.createElement("span");
  dot.style.cssText = "width:9px;height:9px;flex:none;border-radius:50%;background:#8b9298";
  const summary = document.createElement("span");
  summary.textContent = "CFS: checking";
  title.append(dot, summary);
  const refreshButton = document.createElement("button");
  refreshButton.type = "button";
  refreshButton.textContent = "Refresh";
  refreshButton.style.cssText = "min-height:30px;padding:5px 10px;border:1px solid rgba(255,255,255,.2);border-radius:4px;background:#2d3338;color:#fff;cursor:pointer";
  header.append(title, refreshButton);

  const metrics = document.createElement("div");
  metrics.style.cssText = "display:flex;gap:18px;padding:10px 14px;color:#c9d0d5;border-bottom:1px solid rgba(255,255,255,.1)";
  const temperature = document.createElement("span");
  const humidity = document.createElement("span");
  temperature.textContent = "Temp: --";
  humidity.textContent = "Humidity: --";
  metrics.append(temperature, humidity);

  const grid = document.createElement("div");
  grid.style.cssText = "display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:12px 14px";
  const detail = document.createElement("div");
  detail.style.cssText = "display:none;padding:10px 14px 14px;border-top:1px solid rgba(255,255,255,.1);color:#c9d0d5;overflow-wrap:anywhere";
  panel.append(header, metrics, grid, detail);

  let slots = [];
  let selectedSlot = "";
  let refreshInFlight = false;
  let pollTimer = null;

  const displayCode = value => {
    if (value === undefined || value === null || value === "" || value === "-1") return "";
    return String(value);
  };
  const normalizeColor = value => {
    let raw = displayCode(value).trim().toLowerCase().replace(/^0x/, "").replace(/^#/, "");
    if (raw.length === 8) raw = raw.slice(-6);
    if (raw.length > 6) raw = raw.slice(-6);
    return /^[0-9a-f]{6}$/.test(raw) ? "#" + raw : "#69737d";
  };
  const valueOrDash = value => displayCode(value) || "--";

  const renderDetail = slot => {
    detail.replaceChildren();
    if (!slot) {
      detail.style.display = "none";
      return;
    }
    detail.style.display = "block";
    const lines = [
      slot.slot + " · " + (slot.present ? (slot.name || slot.type || "material") : "empty"),
      "Vendor: " + valueOrDash(slot.vendor),
      "RFID: " + valueOrDash(slot.rfid),
      "Remaining: " + (slot.remaining ? slot.remaining + " mm" : "--"),
      "State: " + (slot.selected ? "loaded" : (slot.present ? "available" : "empty")),
    ];
    for (const line of lines) {
      const row = document.createElement("div");
      row.textContent = line;
      row.style.paddingTop = "3px";
      detail.appendChild(row);
    }
  };

  const render = (online, loadedCount) => {
    summary.textContent = "CFS: " + (online ? "online" : "offline") + " · " + loadedCount + " slot(s)";
    dot.style.background = online ? "#39b86b" : "#d85c5c";
    grid.replaceChildren();
    for (const slot of slots) {
      const card = document.createElement("button");
      card.type = "button";
      card.style.cssText = "display:flex;align-items:center;gap:9px;min-width:0;min-height:68px;padding:9px;border:1px solid " + (slot.selected ? normalizeColor(slot.color) : "rgba(255,255,255,.14)") + ";border-radius:5px;background:" + (slot.present ? "#292f34" : "#24282c") + ";color:#f4f5f6;text-align:left;cursor:pointer;opacity:" + (slot.present ? "1" : ".65");
      const swatch = document.createElement("span");
      swatch.style.cssText = "width:26px;height:26px;flex:none;border-radius:50%;background:" + normalizeColor(slot.color) + ";border:2px solid rgba(255,255,255,.4);box-shadow:inset 0 0 0 4px rgba(0,0,0,.12)";
      const text = document.createElement("span");
      text.style.cssText = "display:flex;flex-direction:column;min-width:0;overflow:hidden";
      const name = document.createElement("strong");
      name.textContent = slot.slot + (slot.selected ? " · loaded" : "");
      name.style.whiteSpace = "nowrap";
      name.style.overflow = "hidden";
      name.style.textOverflow = "ellipsis";
      const material = document.createElement("span");
      material.textContent = slot.present ? (slot.name || slot.type || "material") : "empty";
      material.style.cssText = "color:#b9c1c7;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis";
      text.append(name, material);
      card.append(swatch, text);
      card.addEventListener("click", () => {
        selectedSlot = selectedSlot === slot.slot ? "" : slot.slot;
        renderDetail(slots.find(item => item.slot === selectedSlot));
      });
      grid.appendChild(card);
    }
    renderDetail(slots.find(item => item.slot === selectedSlot));
  };

  const parseBox = box => {
    const units = Object.keys(box).filter(key => /^T[1-4]$/.test(key) && box[key] && typeof box[key] === "object");
    const result = [];
    const materialBySlot = new Map();
    if (Array.isArray(box.same_material)) {
      for (const item of box.same_material) {
        if (!Array.isArray(item) || !Array.isArray(item[2])) continue;
        for (const slot of item[2]) {
          materialBySlot.set(String(slot), {
            color: displayCode(item[1]),
            name: displayCode(item[3]),
            materialId: displayCode(item[0]),
          });
        }
      }
    }
    for (const unitName of units) {
      const unit = box[unitName];
      const types = Array.isArray(unit.material_type) ? unit.material_type : [];
      const names = Array.isArray(unit.material_name) ? unit.material_name : [];
      const vendors = Array.isArray(unit.vendor) ? unit.vendor : (Array.isArray(unit.vender) ? unit.vender : []);
      const colors = Array.isArray(unit.color_value) ? unit.color_value : [];
      const rfids = Array.isArray(unit.rfid) ? unit.rfid : [];
      const remaining = Array.isArray(unit.remain_len) ? unit.remain_len : [];
      const selected = Array.isArray(unit.selected) ? unit.selected : [];
      const length = Math.max(4, types.length, names.length, colors.length, rfids.length, remaining.length, selected.length);
      for (let index = 0; index < Math.min(4, length); index++) {
        const slotName = unitName + String.fromCharCode(65 + index);
        const known = materialBySlot.get(slotName) || {};
        const type = displayCode(types[index]);
        const name = displayCode(names[index]) || known.name;
        const color = displayCode(colors[index]) || known.color;
        result.push({
          slot: slotName,
          type,
          name,
          vendor: displayCode(vendors[index]) === "unknown" ? "" : displayCode(vendors[index]),
          color,
          rfid: displayCode(rfids[index]),
          remaining: displayCode(remaining[index]),
          selected: Number(selected[index]) === 1 || unit.filament === slotName,
          present: Boolean(type && type !== "-1" || name || color && color !== "-1" || rfids[index] && rfids[index] !== "-1"),
        });
      }
    }
    return result;
  };

  const refresh = async () => {
    if (refreshInFlight) return;
    refreshInFlight = true;
    refreshButton.disabled = true;
    try {
      const response = await fetch("/printer/objects/query?box", { cache: "no-store" });
      if (!response.ok) throw new Error("Moonraker API " + response.status);
      const payload = await response.json();
      const box = payload?.result?.status?.box;
      if (!box) throw new Error("CFS status unavailable");
      slots = parseBox(box);
      const online = box.is_online === true || box.state === "connect";
      const loadedCount = slots.filter(slot => slot.present).length;
      const firstUnitName = Object.keys(box).find(key => /^T[1-4]$/.test(key) && box[key] && typeof box[key] === "object");
      const firstUnit = firstUnitName ? box[firstUnitName] : {};
      const reportedTemp = box.temp ?? firstUnit.temperature;
      const reportedHumidity = box.humidity ?? firstUnit.dry_and_humidity;
      temperature.textContent = "Temp: " + valueOrDash(reportedTemp) + " C";
      humidity.textContent = "Humidity: " + valueOrDash(reportedHumidity) + "%";
      render(online, loadedCount);
    } catch (error) {
      slots = [];
      temperature.textContent = "Temp: --";
      humidity.textContent = "Humidity: --";
      summary.textContent = "CFS: unavailable";
      dot.style.background = "#e0a23c";
      grid.replaceChildren();
      const message = document.createElement("div");
      message.textContent = "Moonraker did not return the Klipper box status";
      message.style.cssText = "grid-column:1/-1;color:#c9d0d5;padding:4px 0";
      grid.appendChild(message);
      renderDetail(null);
    } finally {
      refreshInFlight = false;
      refreshButton.disabled = false;
    }
  };

  refreshButton.addEventListener("click", refresh);
  const findDashboardContainer = () => {
    const fluiddList = document.querySelector("main .app-draggable.list-group");
    if (fluiddList) return fluiddList;
    return document.querySelector("main");
  };
  const mount = () => {
    if (document.getElementById(rootId)) return true;
    const container = findDashboardContainer();
    if (!container) return false;
    container.appendChild(panel);
    refresh();
    if (!pollTimer) pollTimer = window.setInterval(refresh, 10000);
    return true;
  };
  const tryMount = () => {
    if (mount() && observer) {
      observer.disconnect();
      observer = null;
    }
  };
  let observer = null;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", tryMount, { once: true });
  else tryMount();
  if (!document.getElementById(rootId) && document.body) {
    observer = new MutationObserver(tryMount);
    observer.observe(document.body, { childList: true, subtree: true });
  }
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
    original_html = html
    entrypoint_pattern = re.compile(
        r'(?P<prefix>src=["\'](?P<path>(?:\./)?assets/index-[^"\']+\.js))'
        r'(?:\?[^"\']*)?(?P<quote>["\'])'
    )
    html = entrypoint_pattern.sub(
        lambda match: f'{match.group("prefix")}{match.group("quote")}',
        html,
        count=1,
    )
    if FIRMWARE_BADGE_ID not in html:
        script_tag = f'<script id="{FIRMWARE_BADGE_ID}" defer src="/{FIRMWARE_BADGE_SCRIPT}"></script>'
        if re.search(r"</body\s*>", html, re.IGNORECASE):
            html = re.sub(r"</body\s*>", script_tag + "</body>", html, count=1, flags=re.IGNORECASE)
        elif re.search(r"</html\s*>", html, re.IGNORECASE):
            html = re.sub(r"</html\s*>", script_tag + "</html>", html, count=1, flags=re.IGNORECASE)
        else:
            raise RuntimeError("Fluidd index.html has no body or html closing tag for firmware badge injection.")
    if html != original_html:
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


def patch_file_download(text: str) -> tuple[str, bool]:
    """Patch Fluidd's minified downloadFile method without relying on bundle formatting."""
    marker = "async downloadFile"
    start = text.find(marker)
    while start >= 0:
        open_paren = text.find("(", start + len(marker))
        if open_paren < 0:
            break
        close_paren = text.find(")", open_paren + 1)
        open_brace = text.find("{", close_paren + 1)
        if close_paren < 0 or open_brace < 0:
            break

        depth = 0
        quote = None
        escaped = False
        close_brace = -1
        for position in range(open_brace, len(text)):
            char = text[position]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in "'\"`":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    close_brace = position + 1
                    break
        if close_brace < 0:
            break

        arguments = [item.strip() for item in text[open_paren + 1 : close_paren].split(",")]
        body = text[open_brace:close_brace]
        if len(arguments) >= 2 and (
            "createFileUrlWithToken" in body or "window.location.assign(" in body
        ) and (
            "Sm(" in body
            or "createElement(\"a\")" in body
            or "setAttribute(\"download\"" in body
            or "window.location.assign(" in body
        ):
            replacement = NEW_FILE_DOWNLOAD.replace(
                "downloadFile(e,t)",
                f"downloadFile({text[open_paren + 1 : close_paren]})",
            ).replace(
                "createFileUrlWithToken(e,t)",
                f"createFileUrlWithToken({arguments[0]},{arguments[1]})",
            ).replace(
                'setAttribute(\"download\",e)',
                f'setAttribute(\"download\",{arguments[0]})',
            ).replace(
                "Sm(e,n)",
                f"Sm({arguments[0]},n)",
            )
            return text[:start] + replacement + text[close_brace:], True
        start = text.find(marker, close_brace)

    # Some Fluidd builds contain syntax that makes a full brace scan ambiguous.
    # The download method is immediately followed by createFileUrl in the bundle,
    # so that stable boundary is sufficient for a conservative replacement.
    start = text.find(marker)
    while start >= 0:
        open_paren = text.find("(", start + len(marker))
        close_paren = text.find(")", open_paren + 1)
        if open_paren < 0 or close_paren < 0:
            break
        boundary = re.search(r"}\s*createFileUrl\s*\(", text[close_paren + 1 :])
        if not boundary:
            break
        close_method = close_paren + 1 + boundary.start() + 1
        segment = text[start:close_method]
        arguments = [item.strip() for item in text[open_paren + 1 : close_paren].split(",")]
        if len(arguments) >= 2 and (
            "createFileUrlWithToken" in segment or "window.location.assign(" in segment
        ) and (
            "Sm(" in segment
            or "createElement(\"a\")" in segment
            or "setAttribute(\"download\"" in segment
            or "window.location.assign(" in segment
        ):
            replacement = NEW_FILE_DOWNLOAD.replace(
                "downloadFile(e,t)",
                f"downloadFile({text[open_paren + 1 : close_paren]})",
            ).replace(
                "createFileUrlWithToken(e,t)",
                f"createFileUrlWithToken({arguments[0]},{arguments[1]})",
            ).replace(
                'setAttribute(\"download\",e)',
                f'setAttribute(\"download\",{arguments[0]})',
            ).replace(
                "Sm(e,n)",
                f"Sm({arguments[0]},n)",
            )
            return text[:start] + replacement + text[close_method:], True
        start = text.find(marker, close_method)
    return text, False


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
        elif LEGACY_FILE_DOWNLOAD in download_text:
            download_text = download_text.replace(LEGACY_FILE_DOWNLOAD, NEW_FILE_DOWNLOAD)
        elif NEW_FILE_DOWNLOAD not in download_text:
            download_text, patched = patch_file_download(download_text)
            if not patched:
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
