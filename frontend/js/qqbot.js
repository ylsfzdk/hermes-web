/* ============================================================
   QQ 机器人配置弹窗：左侧「机器人」按钮打开一个独立窗口
   凭据在 QQ 开放平台自己拿（弹窗里给个跳转），本页只负责手填和保存；
   保存走 /_qqbot（后端写 .env + config.yaml，然后重启网关）
   ============================================================ */

import { getCfg, openCfg } from "./config.js";
import { hide, show } from "./common.js";

const $ = (id) => document.getElementById(id);

const mask = $("bot-mask");
const btn = $("bot-btn");
const badge = $("bot-badge");
const appIdEl = $("bot-app-id");
const secretEl = $("bot-secret");
const allowedEl = $("bot-allowed");
const groupEl = $("bot-group-allowed");
const homeEl = $("bot-home");
const enabledEl = $("bot-enabled");
const markdownEl = $("bot-markdown");
const statusEl = $("bot-status");
const saveBtn = $("bot-save");
const gwEl = $("bot-gw");
const logEl = $("bot-log");

// 面板当前状态
let info = null;          // GET /_qqbot 的结果
let authz = "pairing";    // 选中的私聊授权方式
let saving = false;

// ---------- 小工具 ----------
function setStatus(text, kind) {
  statusEl.textContent = text || "";
  statusEl.style.color = kind === "err" ? "#d32f2f" : kind === "ok" ? "#1e8e3e" : "";
}

function api(path, opts = {}) {
  const cfg = getCfg();
  return fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + ((cfg && cfg.key) || ""),
      ...(opts.headers || {})
    }
  });
}

async function jsonOf(res) {
  let body = null;
  try { body = await res.json(); } catch (e) {}
  if (!res.ok) {
    const detail = (body && (body.detail || body.error)) || ("HTTP " + res.status);
    throw new Error(detail);
  }
  return body || {};
}

function splitIds(text) {
  return (text || "").split(",").map(s => s.trim()).filter(Boolean);
}

// ---------- 打开 / 关闭 ----------
export function isBotOpen() {
  return mask.classList.contains("show");
}

export function closeBot() {
  if (!isBotOpen()) return;
  hide(mask);
  btn.classList.remove("active");
}

export function openBot() {
  if (!getCfg()) { openCfg(); return; }
  show(mask);
  btn.classList.add("active");
  loadConfig();
  refreshGateway();
}

// ---------- 读配置 ----------
async function loadConfig() {
  setStatus("读取配置…");
  try {
    const res = await api("/_qqbot");
    info = await jsonOf(res);
    authz = info.dm_authorization || "pairing";
    appIdEl.value = info.app_id || "";
    secretEl.value = "";
    secretEl.placeholder = info.has_secret ? "已配置，留空则不修改" : "输入 AppSecret";
    allowedEl.value = info.allowed_users || "";
    groupEl.value = info.group_allowed_users || "";
    homeEl.value = info.home_channel || "";
    enabledEl.checked = !!info.enabled;
    markdownEl.checked = !!info.markdown_support;
    paintAuthz();
    paintBadge();
    setStatus("");
  } catch (e) {
    info = null;
    setStatus("读取失败：" + e.message, "err");
  }
}

function paintBadge() {
  if (!info) { badge.textContent = ""; badge.className = "bot-badge"; return; }
  if (info.enabled) {
    badge.textContent = "已启用";
    badge.className = "bot-badge on";
  } else {
    badge.textContent = info.has_secret ? "未启用" : "未配置";
    badge.className = "bot-badge";
  }
}

// ---------- 授权方式 ----------
function paintAuthz() {
  const box = $("bot-authz");
  box.innerHTML = "";
  const labels = (info && info.authz_modes) || { pairing: "", allowlist: "", open: "" };
  for (const [mode, desc] of Object.entries(labels)) {
    const row = document.createElement("label");
    row.className = "authz-opt" + (mode === authz ? " sel" : "");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "bot-authz";
    radio.value = mode;
    radio.checked = mode === authz;
    radio.addEventListener("change", () => { authz = mode; paintAuthz(); });
    const text = document.createElement("span");
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = mode === "pairing" ? "配对审批（推荐）"
                  : mode === "allowlist" ? "白名单" : "全部放行（慎用）";
    const d = document.createElement("span");
    d.className = "d";
    d.textContent = desc;
    text.append(t, document.createElement("br"), d);
    row.append(radio, text);
    box.appendChild(row);
  }
  // 白名单只在 allowlist 下是必填，pairing 下可留空
  $("bot-allowed-label").textContent = authz === "allowlist"
    ? "白名单 OpenID（逗号分隔，必填）"
    : "额外放行 OpenID（逗号分隔，可留空）";
}

// ---------- 保存 ----------
async function save() {
  if (saving) return;
  if (authz === "allowlist" && !splitIds(allowedEl.value).length) {
    setStatus("allowlist 模式至少要填一个 OpenID", "err");
    return;
  }
  // 没有扫码自动填了，启用时 AppID / AppSecret 得自己填全（后端也会再拦一次）
  const hasSecret = !!(info && info.has_secret) || !!secretEl.value.trim();
  if (enabledEl.checked && !(appIdEl.value.trim() && hasSecret)) {
    setStatus("启用前先填 AppID 和 AppSecret（在 QQ 开放平台里拿）", "err");
    return;
  }
  saving = true;
  saveBtn.disabled = true;
  setStatus("保存中…");
  try {
    const body = {
      app_id: appIdEl.value.trim(),
      enabled: enabledEl.checked,
      dm_authorization: authz,
      allowed_users: allowedEl.value.trim(),
      group_allowed_users: groupEl.value.trim(),
      home_channel: homeEl.value.trim(),
      markdown_support: markdownEl.checked,
    };
    const secret = secretEl.value.trim();
    if (secret) body.client_secret = secret;

    const res = await api("/_qqbot", { method: "POST", body: JSON.stringify(body) });
    const json = await jsonOf(res);
    if (!json.ok) throw new Error(json.error || json.warning || "保存失败");

    if (!json.changed) {
      setStatus("没有改动", "ok");
    } else if (json.restarting) {
      setStatus("已保存，网关重启中（20–60 秒）…", "ok");
      pollGatewayUntilUp();
    } else if (json.warning) {
      setStatus(json.warning, "err");
    } else {
      setStatus("已保存", "ok");
    }
    await loadConfig();
  } catch (e) {
    setStatus("保存失败：" + e.message, "err");
  } finally {
    saving = false;
    saveBtn.disabled = false;
  }
}

// ---------- 网关状态 + 日志 ----------
// 网关是否在线用现成的 /_gateway_status；qqbot 平台自身状态在网关的 gateway_state.json 里，
// 这里没有直接读它的接口，就用日志里 [QQBot: 开头的行代替。
async function refreshGateway() {
  try {
    const st = await jsonOf(await api("/_gateway_status"));
    paintGateway(st);
  } catch (e) {
    gwEl.textContent = "读取网关状态失败：" + e.message;
    return;
  }
  try {
    const logs = await jsonOf(await api("/_qqbot/log?lines=40"));
    logEl.textContent = (logs.lines || []).join("\n");
    logEl.scrollTop = logEl.scrollHeight;
  } catch (e) {
    logEl.textContent = "";
  }
}

function paintGateway(st) {
  gwEl.innerHTML = "";
  const span = document.createElement("span");
  if (st.restarting) {
    span.textContent = "网关重启中…";
    gwEl.appendChild(span);
    return;
  }
  if (!st.up) {
    span.textContent = "网关没在跑，保存配置后会自动拉起";
    span.style.color = "#d32f2f";
    gwEl.appendChild(span);
    return;
  }
  span.textContent = "网关在线";
  span.style.color = "#1e8e3e";
  gwEl.appendChild(span);
  if (info && info.enabled) gwEl.append("，qqbot 已启用");
}

let gwTimer = null;
function pollGatewayUntilUp() {
  clearInterval(gwTimer);
  let n = 0;
  gwTimer = setInterval(async () => {
    n++;
    await refreshGateway();
    const busy = (gwEl.textContent || "").includes("重启中");
    if (!busy || n > 45) {
      clearInterval(gwTimer);
      gwTimer = null;
      if (!busy) setStatus("网关已就绪", "ok");
    }
  }, 2000);
}

// ---------- 事件绑定 ----------
export function initBot() {
  btn.addEventListener("click", () => {
    if (isBotOpen()) closeBot();
    else openBot();
  });
  saveBtn.addEventListener("click", save);
  gwEl.addEventListener("click", refreshGateway);

  // 关窗口：右上角 ×、点遮罩空白处、Esc。点窗口内部不关
  $("bot-close").addEventListener("click", closeBot);
  mask.addEventListener("click", (e) => {
    if (e.target === mask) closeBot();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isBotOpen()) closeBot();
  });

  // FAQ 折叠
  $("bot-faq").addEventListener("click", (e) => {
    const head = e.target.closest(".faq-head");
    if (head) head.classList.toggle("open");
  });
}