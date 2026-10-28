#!/usr/bin/env python3
"""Install and patch a UDISK-hosted Fluidd copy for the K3 Moonraker API."""

import argparse
import base64
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
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
K3_FILE_API_ORIGIN_MARKER = "k3-file-api-origin-v1"
K3_FILE_API_ORIGIN_METHOD = (
    "createFileUrl(e,t,n){/* k3-file-api-origin-v1 */"
    "let r=(t?`${t}/${e}`:`${e}`).replace(/[^/]+/g,e=>encodeURIComponent(e));"
    "let a=this.apiUrl;try{let o=new URL(a,window.location.origin);"
    "if([\"127.0.0.1\",\"localhost\",\"0.0.0.0\"].includes(o.hostname))"
    "a=window.location.origin}catch{}"
    "return`${a}/server/files/${r}?date=${n||Date.now()}`}"
)
K3_ONESHOT_TOKEN_MARKER = "k3-http-oneshot-token-v1"
K3_ONESHOT_TOKEN_METHOD = (
    "async createFileUrlWithToken(e,t,n){/* k3-http-oneshot-token-v1 */"
    "let r=this.createFileUrl(e,t,n);if(this.isTrustedUser)return r;"
    "try{let i=await fetch(new URL(`/access/oneshot_token`,window.location.origin),"
    "{credentials:`same-origin`});if(i.ok){let a=await i.json();"
    "if(a.result)return`${r}&token=${a.result}`}}catch{}return r}"
)
K3_UPLOAD_ONESHOT_MARKER = "k3-http-upload-oneshot-v1"
K3_UPLOAD_ONESHOT_EXPRESSION = (
    "this.isTrustedUser?null:await(async()=>{/* k3-http-upload-oneshot-v1 */"
    "let r=await fetch(new URL(`/access/oneshot_token`,window.location.origin),"
    "{credentials:`same-origin`});if(!r.ok)throw Error(`Moonraker upload token request failed: ${r.status}`);"
    "let e=await r.json();if(!e.result)throw Error(`Moonraker did not return an upload token`);"
    "return e.result})()"
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
CFS_STATUS_VERSION = "4"
CHAMBER_LIGHT_ID = "creality-chamber-light-script"
CHAMBER_LIGHT_SCRIPT = "creality-chamber-light.js"
CHAMBER_LIGHT_VERSION = "1"
K3_THUMBNAIL_PATCH_MARKER = "k3-thumbnail-fallback-v2"
REPRINT_THUMBNAILS_ID = "creality-reprint-thumbnails-script"
REPRINT_THUMBNAILS_SCRIPT = "creality-reprint-thumbnails.js"
REPRINT_THUMBNAILS_VERSION = "2"

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
  panel.className = "mb-2 mb-md-4 v-card v-sheet rounded-md collapsable-card creality-cfs-status-panel";
  panel.style.cssText = "max-height:min(560px,70vh);overflow:auto;font:13px/1.45 sans-serif";

  const panelStyle = document.createElement("style");
  panelStyle.id = "creality-cfs-status-style";
  panelStyle.textContent = `
    #${rootId} { color: inherit; }
    #${rootId} .creality-cfs-header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
    #${rootId} .creality-cfs-metrics { display:flex; gap:18px; }
    #${rootId} .creality-cfs-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
    #${rootId} .creality-cfs-slot { display:flex; align-items:center; gap:9px; min-width:0; min-height:68px; padding:9px; text-align:left; justify-content:flex-start; }
    #${rootId} .creality-cfs-slot--empty { opacity:.65; }
    #${rootId} .creality-cfs-slot-text { display:flex; flex-direction:column; min-width:0; overflow:hidden; }
    #${rootId} .creality-cfs-slot-name, #${rootId} .creality-cfs-slot-material { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    #${rootId} .creality-cfs-slot-material { opacity:.72; font-size:12px; }
    #${rootId} .creality-cfs-swatch { width:26px; height:26px; flex:none; border-radius:50%; border:2px solid rgba(128,128,128,.5); box-shadow:inset 0 0 0 4px rgba(0,0,0,.12); }
    @media (max-width:600px) { #${rootId} .creality-cfs-grid { grid-template-columns:1fr; } }
  `;
  document.head.appendChild(panelStyle);

  const header = document.createElement("div");
  header.className = "v-card__title collapsable-card-title card-heading creality-cfs-header";
  header.style.cssText = "padding:12px 14px";
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
  refreshButton.className = "v-btn v-btn--outlined v-size--small";
  refreshButton.style.cssText = "min-height:30px;padding:5px 10px;cursor:pointer";
  header.append(title, refreshButton);

  const metrics = document.createElement("div");
  metrics.className = "v-card__text creality-cfs-metrics";
  metrics.style.cssText = "padding:10px 14px";
  const temperature = document.createElement("span");
  const humidity = document.createElement("span");
  temperature.textContent = "Temp: --";
  humidity.textContent = "Humidity: --";
  metrics.append(temperature, humidity);

  const grid = document.createElement("div");
  grid.className = "v-card__text creality-cfs-grid";
  grid.style.cssText = "padding:12px 14px";
  const detail = document.createElement("div");
  detail.className = "v-card__text";
  detail.style.cssText = "display:none;padding:10px 14px 14px;overflow-wrap:anywhere";
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
      card.className = "v-btn v-btn--outlined v-size--small creality-cfs-slot" + (slot.present ? "" : " creality-cfs-slot--empty");
      card.style.borderColor = slot.selected ? normalizeColor(slot.color) : "";
      const swatch = document.createElement("span");
      swatch.className = "creality-cfs-swatch";
      swatch.style.background = normalizeColor(slot.color);
      const text = document.createElement("span");
      text.className = "creality-cfs-slot-text";
      const name = document.createElement("strong");
      name.textContent = slot.slot + (slot.selected ? " · loaded" : "");
      name.className = "creality-cfs-slot-name";
      const material = document.createElement("span");
      material.textContent = slot.present ? (slot.name || slot.type || "material") : "empty";
      material.className = "creality-cfs-slot-material";
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
  const syncThemeClass = () => {
    const app = document.querySelector(".v-application");
    if (!app) return;
    panel.classList.toggle("theme--dark", app.classList.contains("theme--dark"));
    panel.classList.toggle("theme--light", app.classList.contains("theme--light"));
  };
  const findDashboardContainer = () => {
    const path = String(window.location.pathname || "").replace(/\/+$/, "");
    const hash = String(window.location.hash || "").replace(/\?.*$/, "").replace(/\/+$/, "");
    if (path && path !== "/") return null;
    if (hash && hash !== "#" && hash !== "#!") return null;
    const lists = [...document.querySelectorAll("main .app-draggable.list-group")];
    return lists.find(list => [...list.children].some(card => {
      const title = card.querySelector(".collapsable-card-title");
      return title && title.textContent.trim() === "Macros";
    })) || lists[0] || null;
  };
  const mount = () => {
    if (document.getElementById(rootId)) return true;
    const container = findDashboardContainer();
    if (!container) return false;
    const macroCard = [...container.children].find(card => {
      const title = card.querySelector(".collapsable-card-title");
      return title && title.textContent.trim() === "Macros";
    });
    if (macroCard) container.insertBefore(panel, macroCard);
    else container.appendChild(panel);
    syncThemeClass();
    refresh();
    if (!pollTimer) pollTimer = window.setInterval(refresh, 10000);
    return true;
  };
  const unmount = () => {
    const current = document.getElementById(rootId);
    if (current) current.remove();
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  };
  const syncMount = () => {
    if (findDashboardContainer()) {
      mount();
      syncThemeClass();
    } else {
      unmount();
    }
  };
  let observer = null;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", syncMount, { once: true });
  else syncMount();
  window.addEventListener("hashchange", syncMount);
  window.addEventListener("popstate", syncMount);
  if (document.body) {
    observer = new MutationObserver(syncMount);
    observer.observe(document.body, { childList: true, subtree: true });
  }
  const themeObserver = new MutationObserver(syncThemeClass);
  const appElement = document.querySelector(".v-application");
  if (appElement) themeObserver.observe(appElement, { attributes: true, attributeFilter: ["class"] });
})();
'''

CHAMBER_LIGHT_SOURCE = r'''(() => {
  const rootId = "creality-chamber-light-panel";
  if (document.getElementById(rootId)) return;

  const panel = document.createElement("section");
  panel.id = rootId;
  panel.className = "mb-2 mb-md-4 v-card v-sheet rounded-md collapsable-card creality-chamber-light-panel";
  panel.style.cssText = "font:13px/1.45 sans-serif";

  const style = document.createElement("style");
  style.textContent = `
    #${rootId} { color:inherit; }
    #${rootId} .creality-light-header { display:flex;align-items:center;gap:8px;padding:12px 14px;font-weight:700; }
    #${rootId} .creality-light-dot { width:9px;height:9px;flex:none;border-radius:50%;background:#8b9298; }
    #${rootId} .creality-light-row { display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 14px; }
    #${rootId} .creality-light-state { opacity:.72;font-size:12px; }
    #${rootId} .creality-light-actions { display:flex;gap:6px; }
    #${rootId} .creality-light-action { min-width:54px;padding:5px 12px;border:1px solid currentColor;border-radius:4px;background:transparent;color:inherit;cursor:pointer; }
    #${rootId} .creality-light-action[aria-pressed="true"] { background:#3b9c67;color:#fff;border-color:#3b9c67; }
    #${rootId} .creality-light-action:disabled { cursor:wait;opacity:.5; }
    #${rootId} .creality-light-action:focus-visible { outline:2px solid #4d9de0;outline-offset:2px; }
  `;
  document.head.appendChild(style);

  const header = document.createElement("div");
  header.className = "v-card__title collapsable-card-title card-heading creality-light-header";
  const dot = document.createElement("span");
  dot.className = "creality-light-dot";
  const title = document.createElement("span");
  title.textContent = "Chamber light";
  header.append(dot, title);

  const row = document.createElement("div");
  row.className = "v-card__text creality-light-row";
  const state = document.createElement("span");
  state.className = "creality-light-state";
  state.textContent = "Connecting";
  const actions = document.createElement("div");
  actions.className = "creality-light-actions";
  const buttons = [0, 1].map(value => {
    const button = document.createElement("button");
    button.className = "creality-light-action";
    button.type = "button";
    button.textContent = value ? "On" : "Off";
    button.setAttribute("aria-label", `Turn chamber light ${value ? "on" : "off"}`);
    button.setAttribute("aria-pressed", "false");
    button.disabled = true;
    button.addEventListener("click", () => {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      socket.send(JSON.stringify({ method: "set", params: { lightSw: value } }));
      state.textContent = `Command sent: ${value ? "On" : "Off"}`;
    });
    actions.appendChild(button);
    return button;
  });
  row.append(state, actions);
  panel.append(header, row);

  let socket = null;
  let lightState = null;
  let reconnectTimer = null;
  let retryDelay = 1000;
  let mounted = false;

  const render = () => {
    const connected = socket && socket.readyState === WebSocket.OPEN;
    dot.style.background = connected ? "#39b86b" : "#8b9298";
    state.textContent = !connected ? "Disconnected" : lightState === null ? "Connected" : (lightState ? "On" : "Off");
    buttons.forEach((button, index) => {
      button.disabled = !connected;
      button.setAttribute("aria-pressed", lightState === index ? "true" : "false");
    });
  };
  const scheduleReconnect = () => {
    if (reconnectTimer || !mounted) return;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 15000);
  };
  const connect = () => {
    if (!mounted || socket && (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN)) return;
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${scheme}//${window.location.hostname}:9999/`);
    render();
    socket.addEventListener("open", () => {
      retryDelay = 1000;
      render();
    });
    socket.addEventListener("message", event => {
      try {
        const payload = JSON.parse(event.data);
        const value = payload && (payload.lightSw ?? payload.params?.lightSw ?? payload.result?.lightSw);
        if (value === 0 || value === 1 || value === false || value === true) {
          lightState = value === 1 || value === true;
          render();
        }
      } catch {}
    });
    socket.addEventListener("close", () => {
      socket = null;
      lightState = null;
      render();
      scheduleReconnect();
    });
    socket.addEventListener("error", () => socket.close());
  };

  const findDashboard = () => {
    const path = String(window.location.pathname || "").replace(/\/+$/, "");
    const hash = String(window.location.hash || "").replace(/\?.*$/, "").replace(/\/+$/, "");
    if (path && path !== "/") return null;
    if (hash && hash !== "#" && hash !== "#!") return null;
    const lists = [...document.querySelectorAll("main .app-draggable.list-group")];
    return lists.find(list => [...list.children].some(card => {
      const heading = card.querySelector(".collapsable-card-title");
      return heading && heading.textContent.trim() === "Macros";
    })) || lists[0] || null;
  };
  const mount = () => {
    const dashboard = findDashboard();
    if (!dashboard) return false;
    const macros = [...dashboard.children].find(card => {
      const heading = card.querySelector(".collapsable-card-title");
      return heading && heading.textContent.trim() === "Macros";
    });
    if (macros) {
      if (panel.parentElement !== dashboard || panel.nextElementSibling !== macros) {
        dashboard.insertBefore(panel, macros);
      }
    } else if (panel.parentElement !== dashboard || panel !== dashboard.lastElementChild) {
      dashboard.appendChild(panel);
    }
    mounted = true;
    connect();
    return true;
  };
  const unmount = () => {
    mounted = false;
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (socket) {
      const current = socket;
      socket = null;
      current.close();
    }
    panel.remove();
  };
  const syncMount = () => {
    if (findDashboard()) mount();
    else if (mounted) unmount();
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", syncMount, { once: true });
  else syncMount();
  window.addEventListener("hashchange", syncMount);
  window.addEventListener("popstate", syncMount);
  if (document.body) new MutationObserver(syncMount).observe(document.body, { childList: true, subtree: true });
})();
'''

REPRINT_THUMBNAILS_SOURCE = r'''(() => {
  const run = () => {
    for (const table of document.querySelectorAll("table")) {
      const headers = [...table.querySelectorAll("thead th")]
        .map((cell) => cell.textContent.trim().toLowerCase());
      const isReprint = headers.includes("name") && headers.includes("status") &&
        headers.includes("print duration");
      const isFileList = headers.includes("name") && headers.includes("last printed") &&
        headers.includes("modified") && headers.includes("size");
      if (!isReprint && !isFileList) continue;

      for (const row of table.querySelectorAll("tbody tr")) {
        const cells = row.querySelectorAll("td");
        const filename = cells[1]?.textContent.trim();
        if (!filename || !/\.gcode$/i.test(filename) || row.dataset.k3Thumb) continue;

        const stem = filename.replace(/\.gcode$/i, "");
        const image = document.createElement("img");
        image.alt = "";
        image.setAttribute("aria-hidden", "true");
        image.style.cssText = "display:block;width:42px;height:28px;object-fit:contain";
        row.dataset.k3Thumb = "loading";
        image.onload = () => {
          if (!row.isConnected || cells[1]?.textContent.trim() !== filename) return;
          cells[0].replaceChildren(image);
          cells[0].style.verticalAlign = "middle";
          row.dataset.k3Thumb = "loaded";
        };
        image.onerror = () => { row.dataset.k3Thumb = "missing"; };
        image.src = `/server/files/gcodes/.thumbs/${encodeURIComponent(stem)}-300x300.png`;
      }
    }
  };

  run();
  if (document.body) {
    new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
  }
  window.addEventListener("hashchange", run);
})();
'''


def ensure_custom_ui_directory(config_root: Path) -> None:
    """Prepare Fluidd's documented custom UI directory without overwriting user files."""
    theme_dir = config_root / ".fluidd-theme"
    theme_dir.mkdir(parents=True, exist_ok=True)


def default_config_root() -> Path:
    """Use the directory exposed by K3 Moonraker's config file manager when present."""
    moonraker_root = Path("/mnt/SDCARD/cxsw/printer_data/config")
    if moonraker_root.is_dir():
        return moonraker_root
    return Path("/mnt/UDISK/printer_data/config")


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
    script_tag = f'<script id="{CFS_STATUS_ID}" defer src="/{CFS_STATUS_SCRIPT}?v={CFS_STATUS_VERSION}"></script>'
    existing_pattern = re.compile(
        rf'<script\s+id=["\']{re.escape(CFS_STATUS_ID)}["\'][^>]*></script>',
        re.IGNORECASE,
    )
    if existing_pattern.search(html):
        html = existing_pattern.sub(script_tag, html, count=1)
    else:
        if re.search(r"</body\s*>", html, re.IGNORECASE):
            html = re.sub(r"</body\s*>", script_tag + "</body>", html, count=1, flags=re.IGNORECASE)
        elif re.search(r"</html\s*>", html, re.IGNORECASE):
            html = re.sub(r"</html\s*>", script_tag + "</html>", html, count=1, flags=re.IGNORECASE)
        else:
            raise RuntimeError("Fluidd index.html has no body or html closing tag for CFS status injection.")
    index.write_text(html, encoding="utf-8")


def install_chamber_light_display(root: Path) -> None:
    (root / CHAMBER_LIGHT_SCRIPT).write_text(CHAMBER_LIGHT_SOURCE, encoding="utf-8")
    index = root / "index.html"
    html = index.read_text(encoding="utf-8")
    script_tag = (
        f'<script id="{CHAMBER_LIGHT_ID}" defer '
        f'src="/{CHAMBER_LIGHT_SCRIPT}?v={CHAMBER_LIGHT_VERSION}"></script>'
    )
    existing_pattern = re.compile(
        rf'<script\s+id=["\']{re.escape(CHAMBER_LIGHT_ID)}["\'][^>]*></script>',
        re.IGNORECASE,
    )
    if existing_pattern.search(html):
        html = existing_pattern.sub(script_tag, html, count=1)
    elif re.search(r"</body\s*>", html, re.IGNORECASE):
        html = re.sub(r"</body\s*>", script_tag + "</body>", html, count=1, flags=re.IGNORECASE)
    elif re.search(r"</html\s*>", html, re.IGNORECASE):
        html = re.sub(r"</html\s*>", script_tag + "</html>", html, count=1, flags=re.IGNORECASE)
    else:
        raise RuntimeError("Fluidd index.html has no body or html closing tag for chamber light control.")
    index.write_text(html, encoding="utf-8")


def install_reprint_thumbnail_display(root: Path) -> None:
    (root / REPRINT_THUMBNAILS_SCRIPT).write_text(
        REPRINT_THUMBNAILS_SOURCE, encoding="utf-8"
    )
    index = root / "index.html"
    html = index.read_text(encoding="utf-8")
    script_tag = (
        f'<script id="{REPRINT_THUMBNAILS_ID}" defer '
        f'src="/{REPRINT_THUMBNAILS_SCRIPT}?v={REPRINT_THUMBNAILS_VERSION}"></script>'
    )
    existing_pattern = re.compile(
        rf'<script\s+id=["\']{re.escape(REPRINT_THUMBNAILS_ID)}["\'][^>]*></script>',
        re.IGNORECASE,
    )
    if existing_pattern.search(html):
        html = existing_pattern.sub(script_tag, html, count=1)
    elif re.search(r"</body\s*>", html, re.IGNORECASE):
        html = re.sub(r"</body\s*>", script_tag + "</body>", html, count=1, flags=re.IGNORECASE)
    elif re.search(r"</html\s*>", html, re.IGNORECASE):
        html = re.sub(r"</html\s*>", script_tag + "</html>", html, count=1, flags=re.IGNORECASE)
    else:
        raise RuntimeError("Fluidd index.html has no body or html closing tag for reprint thumbnails.")
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


def patch_file_api_origin(text: str) -> tuple[str, bool]:
    """Use Fluidd's origin when K3 advertises Moonraker as loopback.

    K3's websocket endpoint is reachable through nginx, but its Fluidd build
    reports ``http://127.0.0.1:7125`` as ``apiUrl``.  A browser on another
    computer consequently sends editor/download requests to itself.
    """
    if K3_FILE_API_ORIGIN_MARKER in text:
        return text, False

    marker = re.compile(r"(?<![.$\w])createFileUrl\((\w+),(\w+),(\w+)\)\{")
    match = marker.search(text)
    if not match:
        return text, False
    start = match.start()
    open_brace = match.end() - 1
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
        return text, False

    method = K3_FILE_API_ORIGIN_METHOD.replace(
        "createFileUrl(e,t,n)",
        f"createFileUrl({match.group(1)},{match.group(2)},{match.group(3)})",
    ).replace(
        "`${t}/${e}`",
        "`${" + match.group(2) + "}/${" + match.group(1) + "}`",
    )
    # The replacement above keeps the generated method independent of the
    # minifier's local variable names while retaining its original behavior.
    return text[:start] + method + text[close_brace:], True


def patch_http_oneshot_token(text: str) -> tuple[str, bool]:
    """Use Moonraker's HTTP token endpoint instead of its missing K3 RPC."""
    if K3_ONESHOT_TOKEN_MARKER in text:
        return text, False

    marker = re.compile(r"(?<![.$\w])async createFileUrlWithToken\((\w+),(\w+),(\w+)\)\{")
    match = marker.search(text)
    if not match:
        return text, False
    start = match.start()
    open_brace = match.end() - 1
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
        return text, False

    method = K3_ONESHOT_TOKEN_METHOD.replace(
        "createFileUrlWithToken(e,t,n)",
        f"createFileUrlWithToken({match.group(1)},{match.group(2)},{match.group(3)})",
    ).replace("this.createFileUrl(e,t,n)", f"this.createFileUrl({match.group(1)},{match.group(2)},{match.group(3)})")
    return text[:start] + method + text[close_brace:], True


def patch_http_upload_oneshot_token(text: str) -> tuple[str, bool]:
    """Use Moonraker's HTTP token endpoint before uploading edited files."""
    if K3_UPLOAD_ONESHOT_MARKER in text:
        return text, False

    marker = re.compile(r"(?<![.$\w])async serverFilesUploadPost\(([^)]*)\)\{")
    match = marker.search(text)
    if not match:
        return text, False
    start = match.start()
    open_brace = match.end() - 1
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
        return text, False

    method = text[start:close_brace]
    token_call = re.compile(r"this\.isTrustedUser\?null:await\s+\w+\.accessOneshotToken\(\)")
    method, count = token_call.subn(K3_UPLOAD_ONESHOT_EXPRESSION, method, count=1)
    if count != 1:
        return text, False
    return text[:start] + method + text[close_brace:], True


def patch_bundle(root: Path) -> None:
    list_matches = []
    delete_matches = []
    download_matches = []
    thumbnail_matches = []
    file_api_matches = []
    token_matches = []
    upload_token_matches = []
    for asset in (root / "assets").glob("*.js"):
        text = asset.read_text(encoding="utf-8")
        if "setWebcamsList(" in text:
            list_matches.append((asset, text))
        if "serverWebcamsDelete(" in text and "server.webcams.delete_item" in text:
            delete_matches.append((asset, text))
        if "async downloadFile(" in text and "createFileUrlWithToken" in text:
            download_matches.append((asset, text))
        if "getThumb(" in text and "relative_path" in text:
            thumbnail_matches.append((asset, text))
        if re.search(r"(?<![.$\w])createFileUrl\(\w+,\w+,\w+\)\{", text) and "/server/files/" in text:
            file_api_matches.append((asset, text))
        if "async createFileUrlWithToken(" in text and "accessOneshotToken" in text:
            token_matches.append((asset, text))
        if "async serverFilesUploadPost(" in text and "accessOneshotToken" in text:
            upload_token_matches.append((asset, text))

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

    if not file_api_matches:
        raise RuntimeError("Could not find Fluidd file API URL module.")

    for file_api_asset, _ in file_api_matches:
        file_api_text = file_api_asset.read_text(encoding="utf-8")
        file_api_text, _ = patch_file_api_origin(file_api_text)
        if K3_FILE_API_ORIGIN_MARKER not in file_api_text:
            raise RuntimeError(
                f"Fluidd file API URL code did not match a supported version: {file_api_asset.name}"
            )
        file_api_asset.write_text(file_api_text, encoding="utf-8")

    if not token_matches:
        raise RuntimeError("Could not find Fluidd one-shot token module.")

    for token_asset, _ in token_matches:
        token_text = token_asset.read_text(encoding="utf-8")
        token_text, _ = patch_http_oneshot_token(token_text)
        if K3_ONESHOT_TOKEN_MARKER not in token_text:
            raise RuntimeError(
                f"Fluidd one-shot token code did not match a supported version: {token_asset.name}"
            )
        token_asset.write_text(token_text, encoding="utf-8")

    if not upload_token_matches:
        raise RuntimeError("Could not find Fluidd file-upload one-shot token module.")

    for upload_asset, _ in upload_token_matches:
        upload_text = upload_asset.read_text(encoding="utf-8")
        upload_text, _ = patch_http_upload_oneshot_token(upload_text)
        if K3_UPLOAD_ONESHOT_MARKER not in upload_text:
            raise RuntimeError(
                f"Fluidd file-upload token code did not match a supported version: {upload_asset.name}"
            )
        upload_asset.write_text(upload_text, encoding="utf-8")

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

    thumbnail_patched = False
    for thumbnail_asset, _ in thumbnail_matches:
        # Earlier compatibility passes may have edited this same bundle.
        # Reload it here so the thumbnail patch cannot erase webcam/download fixes.
        thumbnail_text = thumbnail_asset.read_text(encoding="utf-8")
        thumbnail_text, patched = patch_thumbnail_getter(thumbnail_text)
        if patched or K3_THUMBNAIL_PATCH_MARKER in thumbnail_text:
            thumbnail_patched = True
        else:
            continue
        thumbnail_asset.write_text(thumbnail_text, encoding="utf-8")
    if not thumbnail_patched:
        print("K3 thumbnail fallback was not added; Fluidd will use Moonraker metadata.", file=sys.stderr)


def patch_thumbnail_getter(text: str) -> tuple[str, bool]:
    """Use K3-extracted sidecar thumbnails when Moonraker metadata lacks them."""
    if K3_THUMBNAIL_PATCH_MARKER in text:
        return text, False
    # Match the class method declaration, not the `this.getThumb(...)` call
    # made by getThumbUrl immediately before it.
    marker = re.compile(r"(?<![.$\w])getThumb\(")
    match = marker.search(text)
    start = match.start() if match else -1
    while start >= 0:
        open_paren = start + len("getThumb")
        close_paren = text.find(")", open_paren + 1)
        open_brace = text.find("{", close_paren + 1)
        if close_paren < 0 or open_brace < 0:
            return text, False

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
            return text, False

        args = [value.strip() for value in text[open_paren + 1 : close_paren].split(",")]
        body = text[open_brace:close_brace]
        if len(args) >= 3 and "thumbnails" in body and "createFileUrl" in body:
            file_arg, root_arg, path_arg = args[:3]
            large_arg = args[3].split("=", 1)[0].strip() if len(args) > 3 else "large"
            date_arg = args[4] if len(args) > 4 else "date"
            replacement = (
                f"/* {K3_THUMBNAIL_PATCH_MARKER} */"
                f"getThumb({','.join(args)}){{"
                f"if({file_arg}.thumbnails?.length){{"
                f"const thumbs={file_arg}.thumbnails;"
                f"const thumb=thumbs.reduce((a,b)=>(a.size>b.size)==={large_arg}?a:b);"
                "if(thumb.relative_path){"
                f"const filepath={path_arg}?`${{{root_arg}}}/${{{path_arg}}}`:{root_arg};"
                f"return{{...thumb,url:this.createFileUrl(thumb.relative_path,filepath,{date_arg})}}"
                "}"
                "}"
                f"if(!/\\.gcode$/i.test({file_arg}.filename||\"\"))return;"
                f"const filepath={path_arg}?`${{{root_arg}}}/${{{path_arg}}}`:{root_arg};"
                f"const relativePath=`.thumbs/${{{file_arg}.filename.replace(/\\.gcode$/i,\"\")}}-300x300.png`;"
                f"return{{width:300,height:300,size:0,relative_path:relativePath,url:this.createFileUrl(relativePath,filepath,{date_arg})}}"
                "}"
            )
            return text[:start] + replacement + text[close_brace:], True
        match = marker.search(text, close_brace)
        start = match.start() if match else -1
    return text, False


def generate_k3_thumbnail_sidecars() -> int:
    """Extract embedded G-code preview PNGs into Moonraker's static file root."""
    roots_url = "http://127.0.0.1:7125/server/files/roots"
    with urllib.request.urlopen(roots_url, timeout=10) as response:
        roots = json.loads(response.read()).get("result", [])
    gcode_root = next((Path(item["path"]) for item in roots if item.get("name") == "gcodes"), None)
    if gcode_root is None or not gcode_root.is_dir():
        raise RuntimeError("Could not resolve Moonraker's registered gcodes root.")

    generated = 0
    marker = re.compile(
        rb";\s*thumbnail(?:_[A-Za-z0-9]+)?\s+begin\s+"
        rb"(\d+)x(\d+)\s+(\d+)\s*\r?\n"
        rb"(.*?)"
        rb";[ \t]*thumbnail(?:_[A-Za-z0-9]+)?\s+end",
        re.DOTALL | re.IGNORECASE,
    )
    for gcode in gcode_root.rglob("*.gcode"):
        try:
            with gcode.open("rb") as source:
                data = source.read(1024 * 1024)
            matches = []
            for match in marker.finditer(data):
                width, height, expected_size = map(int, match.group(1, 2, 3))
                encoded = b"".join(
                    line.strip()[1:].strip()
                    for line in match.group(4).splitlines()
                    if line.strip().startswith(b";")
                )
                if len(encoded) != expected_size:
                    continue
                image = base64.b64decode(encoded, validate=True)
                if (
                    image.startswith(b"\x89PNG\r\n\x1a\n")
                    and width > 0
                    and height > 0
                ):
                    matches.append((width * height, image))
            if not matches:
                continue
            thumb_dir = gcode.parent / ".thumbs"
            thumb_dir.mkdir(exist_ok=True)
            target = thumb_dir / (gcode.stem + "-300x300.png")
            if target.exists():
                continue
            temp = target.with_name(target.name + ".tmp")
            temp.write_bytes(max(matches, key=lambda item: item[0])[1])
            temp.replace(target)
            generated += 1
        except (OSError, ValueError, base64.binascii.Error):
            continue
    return generated


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
    config_root: Path,
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
    install_chamber_light_display(destination)
    install_reprint_thumbnail_display(destination)
    ensure_custom_ui_directory(config_root)
    try:
        generated = generate_k3_thumbnail_sidecars()
        if generated:
            print(f"Generated {generated} K3 G-code thumbnail sidecar(s).")
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"K3 thumbnail extraction skipped: {exc}", file=sys.stderr)
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
    parser.add_argument(
        "--config-root",
        type=Path,
        default=default_config_root(),
    )
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        install(
            args.source,
            args.destination,
            args.nginx,
            args.firmware_version,
            args.config_root,
            args.refresh,
        )
    except Exception as exc:
        print(f"K3 Fluidd compatibility setup failed: {exc}", file=sys.stderr)
        return 1
    print("Fluidd patched for K3 compatibility, firmware version display, and Custom UI support.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
