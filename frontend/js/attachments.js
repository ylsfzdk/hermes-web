/* ============================================================
   会话级附件：输入框下面那行左边的 📎 按钮
   选文件 → 客户端先校验（格式 / 大小）→ 传到后端再校验一次 →
   存进 $HERMES_HOME/sessions/<会话ID>/attachments/，跟会话绑死
   ============================================================ */

import { API_BASE } from "./common.js";
import { getCfg, openCfg } from "./config.js";

const MAX_BYTES = 20 * 1024 * 1024;

// 和后端 attachments.TYPES 保持一致（后端是最终判据，这里只为选文件时就拦掉）
const TYPES = {
  pdf: "PDF", doc: "Word", docx: "Word", odt: "OpenDocument 文本", rtf: "RTF",
  txt: "纯文本", md: "Markdown", markdown: "Markdown", csv: "CSV", tsv: "TSV",
  epub: "EPUB", mobi: "Mobi",
  xls: "Excel", xlsx: "Excel", xlsm: "Excel（宏）", ods: "OpenDocument 表格",
  numbers: "Numbers",
  ppt: "PowerPoint", pptx: "PowerPoint", ppsx: "PowerPoint 放映",
  odp: "OpenDocument 演示", key: "Keynote",
  png: "PNG", jpg: "JPEG", jpeg: "JPEG", gif: "GIF", webp: "WebP", bmp: "BMP",
  tif: "TIFF", tiff: "TIFF", svg: "SVG", ico: "图标", avif: "AVIF", heic: "HEIC",
  py: "Python", js: "JavaScript", mjs: "JavaScript", cjs: "JavaScript",
  ts: "TypeScript", tsx: "TypeScript", jsx: "JavaScript", java: "Java",
  kt: "Kotlin", c: "C", h: "C 头文件", cpp: "C++", hpp: "C++ 头文件", cs: "C#",
  go: "Go", rs: "Rust", rb: "Ruby", php: "PHP", swift: "Swift", scala: "Scala",
  r: "R", lua: "Lua", dart: "Dart", m: "Objective-C / MATLAB", sh: "Shell",
  bat: "批处理", ps1: "PowerShell", sql: "SQL", html: "HTML", htm: "HTML",
  css: "CSS", scss: "SCSS", less: "Less", vue: "Vue", svelte: "Svelte",
  xml: "XML", yaml: "YAML", yml: "YAML", toml: "TOML", ini: "INI", cfg: "配置",
  conf: "配置", env: "环境变量", json: "JSON", jsonl: "JSON Lines", log: "日志",
  tex: "LaTeX", rst: "reStructuredText", properties: "Properties", gradle: "Gradle",
};
// 单个按钮能选的文件格式（"*/*" 会让手机相册/文件管理全放出来）
const ACCEPT = Object.keys(TYPES).map(e => "." + e).join(",");

const btn = document.getElementById("file-btn");
const fileInput = document.getElementById("file-input");
const chipsEl = document.getElementById("file-chips");

let sessionId = null;   // 当前会话，由 chat.js 同步进来
let files = [];         // [{ id, name, type, size }]
let busy = false;

export function setAttachmentSession(sid) {
  if (sid === sessionId) return;
  sessionId = sid;
  files = [];           // 换会话就清空，附件跟着会话走
  render();
  listFiles();          // 恢复这个会话之前传过的附件
}

// 附件有无变化时通知外部（chat.js 据此决定发送按钮是否可选）
export const hooks = { changed: null };

export function bindAttachments({ ensureSession, notify }) {
  fileInput.accept = ACCEPT;
  btn.addEventListener("mousedown", (e) => e.preventDefault());  // 别让输入框丢焦点
  btn.addEventListener("click", async () => {
    if (busy) return;
    if (!getCfg()) { openCfg(); return; }
    if (!sessionId) {
      sessionId = await ensureSession();   // 先给附件找个会话目录
      if (!sessionId) return;
    }
    fileInput.click();
  });
  fileInput.addEventListener("change", (ev) => onPick(ev, notify));
}

export const attachmentNames = () => files.filter(f => !f.error).map(f => f.name);

// 基础校验：格式 + 大小。返回错误文案，通过返回 null。
export function checkFile(file) {
  const name = file.name || "";
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  if (!ext) return "不支持的文件格式（没有扩展名）";
  if (!(ext in TYPES)) return "不支持的文件格式：." + ext;
  if (file.size <= 0) return "文件是空的";
  if (file.size > MAX_BYTES) return "太大（上限 20 MB）";
  return null;
}

function render() {
  chipsEl.innerHTML = "";
  for (const f of files) {
    const chip = document.createElement("span");
    chip.className = "file-chip" + (f.error ? " bad" : "");
    chip.title = f.error ? f.name + "：" + f.error : f.name;

    const name = document.createElement("span");
    name.className = "chip-name";
    name.textContent = f.name;

    const meta = document.createElement("span");
    meta.className = "chip-meta";
    meta.textContent = f.error ? f.error : f.type;

    const x = document.createElement("button");
    x.type = "button";
    x.className = "chip-x";
    x.textContent = "×";
    x.title = "移除";
    x.addEventListener("click", () => {
      files = files.filter(y => y !== f);
      render();
    });

    chip.append(name, meta, x);
    chipsEl.appendChild(chip);
  }
  if (hooks.changed) hooks.changed();
}

// 当前有没有"能算数"的附件（有效且待发/已落盘），供发送按钮判断可用性
export const hasAttachments = () => files.some(f => !f.error);

async function upload(file, sid, commit = true) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(
    API_BASE + "/_attachments?session_id=" + encodeURIComponent(sid) + (commit ? "" : "&commit=0"),
    {
      method: "POST",
      headers: { "Authorization": "Bearer " + ((getCfg() || {}).key || "") },
      body: fd
    });
  let json = {};
  try { json = await res.json(); } catch (e) {}
  if (!res.ok || !json.ok) throw new Error(json.error || "HTTP " + res.status);
  return json.file;
}

// 点发送时才真正写盘：先让后端把文件验一遍，全过了再一个个落盘。
// 返回错误文案，全部成功返回 null。
export async function commitPending() {
  const ok = files.filter(f => f.pending && !f.error);
  for (const f of ok) {
    try {
      const item = await upload(f.file, sessionId, true);
      Object.assign(f, { id: item.id, name: item.name, type: item.type, size: item.size });
      delete f.file;
      delete f.pending;
    } catch (e) {
      f.error = e.message;
      render();
      return "上传失败：" + f.name + "：" + e.message;
    }
  }
  // 落盘成功后标签就该消失了：文件已经跟着这条消息发出去，不留在输入框
  files = files.filter(f => !ok.includes(f));
  render();
  markSent(ok);
  return null;
}

// 告诉后端这些文件已经随消息发出，刷新时别再当"待发附件"恢复回来
function markSent(items) {
  const ids = items.map(f => f.id).filter(Boolean);
  if (!ids.length || !sessionId) return;
  fetch(API_BASE + "/_attachments/sent?session_id=" + encodeURIComponent(sessionId), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + ((getCfg() || {}).key || "")
    },
    body: JSON.stringify({ ids })
  }).catch(() => {});
}

// 选文件时只预检不写盘，文件先留在浏览器里，点发送才落盘
async function onPick(ev, notify) {
  const picked = Array.from(ev.target.files || []);
  ev.target.value = "";            // 同一个文件再选一次也能触发
  if (!picked.length || busy) return;

  busy = true;
  btn.disabled = true;
  try {
    if (!sessionId && !(sessionId = await ensureSession())) return;
    for (const f of picked) {
      const bad = checkFile(f);
      if (bad) {
        files.push({ name: f.name, type: "", size: f.size, error: bad });
        render();
        continue;
      }
      try {
        const info = await upload(f, sessionId, false);
        files.push({
          file: f, pending: true,
          name: info.name, type: info.type, size: info.size,
        });
      } catch (e) {
        files.push({ name: f.name, type: "", size: f.size, error: e.message });
        if (notify) notify("文件校验未通过：" + f.name + "：" + e.message);
      }
      render();
    }
  } finally {
    busy = false;
    btn.disabled = false;
  }
}

// 刷新/换会话时只恢复还没发出去的标签；已落盘的是历史附件，不该占着输入框
async function listFiles() {
  if (!sessionId) return;
  try {
    const res = await fetch(API_BASE + "/_attachments?session_id=" + encodeURIComponent(sessionId),
      { headers: { "Authorization": "Bearer " + ((getCfg() || {}).key || "") } });
    const json = await res.json();
    if (json && json.ok && Array.isArray(json.files)) {
      const pending = files.filter(f => f.pending || f.error);
      files = pending.concat(
        json.files.filter(x => x.sent === false).map(x => ({
          id: x.id, name: x.name, type: x.type, size: x.size
        })));
      render();
    }
  } catch (e) {}
}