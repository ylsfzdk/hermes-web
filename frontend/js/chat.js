/* ============================================================
   聊天主逻辑：会话列表、消息渲染、SSE 流式回复
   ============================================================ */

import { API_BASE } from "./common.js";
import { getCfg } from "./config.js";
import { openCfg } from "./config.js";
import {
  attachmentNames, bindAttachments, commitPending, hasAttachments, setAttachmentSession
} from "./attachments.js";
import { hooks as attachmentHooks } from "./attachments.js";

const CUR_WS = "hermes.currentWs";

// ============ DOM ============
const chatInner = document.getElementById("chat-inner");
const chat = document.getElementById("chat");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send-btn");
const wsList = document.getElementById("ws-list");
const newWsBtn = document.getElementById("new-ws");
const sidebar = document.getElementById("sidebar");
const toggleBtn = document.getElementById("toggle-sidebar");
const topbarTitle = document.getElementById("topbar-title");

// ============ 状态 ============
let sessions = [];        // 会话列表
// 注意：跨模块读取一定要用 currentId()，export 出去的 let 是快照，不会跟着变
let currentId = localStorage.getItem(CUR_WS) || null;
export const getCurrentId = () => currentId;
let controller = null;    // AbortController

// ============ 工具函数 ============
function api(path, opts = {}) {
  const cfg = getCfg();
  return fetch(API_BASE + path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + ((cfg && cfg.key) || ""),
      ...(opts.headers || {})
    }
  });
}

export function showError(msg) {
  addMsg("system", msg);
}

// ============ 消息渲染 ============
function addMsg(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  const b = document.createElement("div");
  b.className = "bubble";
  b.textContent = text;
  div.appendChild(b);
  chatInner.appendChild(div);
  scrollBottom();
  return b;
}

function addToolCard(name, preview) {
  const div = document.createElement("div");
  div.className = "tool-card";
  div.textContent = `⚙ ${name}${preview ? "：" + preview : ""}`;
  chatInner.appendChild(div);
  scrollBottom();
  return div;
}

function scrollBottom(force) {
  if (force !== false) {
    const near = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 200;
    if (near) chat.scrollTop = chat.scrollHeight;
  }
}

// ============ 会话列表 ============
export async function loadSessions() {
  if (!getCfg()) { renderWsList(); return; }
  try {
    const res = await api("/api/sessions?limit=50");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const json = await res.json();
    sessions = json.data || [];
  } catch (e) {
    sessions = [];
  }
  renderWsList();
}

function renderWsList() {
  wsList.innerHTML = "";
  const visible = sessions.filter(s => s.source === "api_server" || !s.source);
  if (!visible.length) {
    wsList.innerHTML = '<div class="ws-empty">还没有工作区<br>点上方按钮新建</div>';
    return;
  }
  for (const s of visible) {
    const item = document.createElement("div");
    item.className = "ws-item" + (s.id === currentId ? " active" : "");
    item.dataset.id = s.id;

    const title = document.createElement("span");
    title.className = "ws-title";
    title.textContent = s.title || s.preview || "未命名";

    const del = document.createElement("button");
    del.className = "ws-del";
    del.type = "button";
    del.textContent = "×";
    del.title = "删除";
    del.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (!confirm(`删除「${title.textContent}」？`)) return;
      await deleteSession(s.id);
    });

    item.appendChild(title);
    item.appendChild(del);
    item.addEventListener("click", () => switchSession(s.id));
    wsList.appendChild(item);
  }
}

async function deleteSession(id) {
  try {
    const res = await api("/api/sessions/" + encodeURIComponent(id), { method: "DELETE" });
    if (!res.ok && res.status !== 404) throw new Error("HTTP " + res.status);
  } catch (e) {
    showError("删除失败：" + e.message);
    return;
  }
  // 网关只删 state.db 里的记录，sessions/<id>/ 目录还在，附件得自己清
  try {
    const res = await fetch(API_BASE + "/_attachments?session_id=" + encodeURIComponent(id),
      { method: "DELETE" });
    if (!res.ok) throw new Error("HTTP " + res.status);
  } catch (e) {
    showError("会话已删除，但附件目录清理失败：" + e.message);
  }
  if (id === currentId) {
    currentId = null;
    localStorage.removeItem(CUR_WS);
    clearDraft(id);
    setAttachmentSession(null);
    chatInner.innerHTML = "";
    topbarTitle.textContent = "Hermes Web";
  }
  await loadSessions();
}

// ============ 草稿 ============
// 按会话 ID 存 localStorage，切走时写、切回时读、发出去了就删。
// 没发出去的输入框内容换个会话再回来还在，刷新也不丢。
const DRAFT_PREFIX = "hermes.draft.";

function saveDraft(sid, text) {
  if (!sid) return;
  try {
    if (text.trim()) localStorage.setItem(DRAFT_PREFIX + sid, text);
    else localStorage.removeItem(DRAFT_PREFIX + sid);
  } catch (e) {}   // 隐私模式/配额满，草稿丢了也不该影响聊天
}

function loadDraft(sid) {
  if (!sid) return "";
  try { return localStorage.getItem(DRAFT_PREFIX + sid) || ""; } catch (e) { return ""; }
}

function clearDraft(sid) {
  if (!sid) return;
  try { localStorage.removeItem(DRAFT_PREFIX + sid); } catch (e) {}
}

// ============ 切换 / 新建会话 ============
export async function switchSession(id) {
  if (controller) { controller.abort(); controller = null; }
  // 离开当前会话：把没发出去的输入框内容存成草稿
  if (currentId && currentId !== id) saveDraft(currentId, input.value);
  const sameSession = currentId === id;
  currentId = id;
  localStorage.setItem(CUR_WS, id);
  setAttachmentSession(id);
  // 切回会话或刷新页面时读这个会话的草稿。
  // 有草稿就填，没有就清空——别留着上个会话的字。
  // 同一会话重载（改配置）时输入框里已经有字，不覆盖
  if (!sameSession || !input.value.trim()) input.value = loadDraft(id);
  refreshSendState();
  chatInner.innerHTML = "";
  renderWsList();

  const s = sessions.find(x => x.id === id);
  topbarTitle.textContent = (s && (s.title || s.preview)) || "工作区";

  try {
    const res = await api("/api/sessions/" + encodeURIComponent(id) + "/messages");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const json = await res.json();
    for (const m of (json.data || [])) {
      if (m.role === "user" || m.role === "assistant") {
        if (m.content && String(m.content).trim()) addMsg(m.role, m.content);
      } else if (m.role === "tool") {
        // 工具结果不显示正文，避免刷屏
      }
    }
  } catch (e) {
    showError("加载历史失败：" + e.message);
  }
  scrollBottom();

  if (window.innerWidth <= 720) sidebar.classList.add("collapsed");
}

async function createWorkspace() {
  if (!getCfg()) { openCfg(); return; }
  try {
    const res = await api("/api/sessions", { method: "POST", body: JSON.stringify({}) });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const json = await res.json();
    await loadSessions();
    await switchSession(json.session.id);
    input.focus();
  } catch (e) {
    showError("新建工作区失败：" + e.message);
  }
}

// ============ 发消息 ============
let streaming = false;   // 正在生成，此时按钮是"停止"，永远可点

// 输入框没字、也没有附件时，发送按钮不可选，悬停也不变色
function refreshSendState() {
  const usable = !!(input.value.trim() || hasAttachments());
  sendBtn.disabled = !streaming && !usable;
}

function setBusy(busy) {
  streaming = busy;
  if (busy) {
    sendBtn.textContent = "停止";
    sendBtn.classList.add("stop");
  } else {
    sendBtn.textContent = "发送";
    sendBtn.classList.remove("stop");
  }
  refreshSendState();
}

async function ensureSession(firstText) {
  if (currentId) return currentId;
  // 没有会话就建一个，标题用首条消息前 20 字
  const title = firstText.slice(0, 20);
  const res = await api("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title })
  });
  if (!res.ok) throw new Error("无法创建会话 HTTP " + res.status);
  const json = await res.json();
  currentId = json.session.id;
  localStorage.setItem(CUR_WS, currentId);
  topbarTitle.textContent = title;
  return currentId;
}

// 从 state.db 取会话历史，转成 OpenAI messages。
// /v1/chat/completions 不走会话记忆，历史必须自己带上。
async function buildHistory(sid) {
  const res = await api("/api/sessions/" + encodeURIComponent(sid) + "/messages");
  if (!res.ok) throw new Error("加载历史失败 HTTP " + res.status);
  const json = await res.json();
  return (json.data || [])
    .filter(m => (m.role === "user" || m.role === "assistant") && m.content && String(m.content).trim())
    .map(m => ({ role: m.role, content: String(m.content) }));
}

async function sendMessage(text, names = []) {
  const sid0 = await ensureSession(text);
  // 附件在点发送这一刻才真正写盘；写失败就不发，把消息留在输入框
  const failed = await commitPending();
  if (failed) { showError(failed); loadSessions(); return; }

  // 附件只随这条消息进上下文：把文件名交代清楚，模型自己去读
  const shown = names.length
    ? `[附件] ${names.join("、")}\n${text}`
    : text;
  addMsg("user", shown);
  input.value = "";
  setBusy(true);

  // 用户消息已经进了上下文，从这里开始就算"发送成功"，草稿该删了。
  // 之后无论是模型报错还是用户点停止，都不该把文字塞回输入框。
  let ok = false;
  let toolCard = null;

  try {
    const sid = sid0 || await ensureSession(text);
    const history = await buildHistory(sid);

    // 走 /v1/chat/completions 而不是 /api/sessions/{id}/chat/stream：
    // 只有前者在客户端断开时会调 agent.interrupt()，真正掐断推理。
    // X-Hermes-Session-Id 让这一轮落进当前会话，会话列表里能看到。
    controller = new AbortController();
    const res = await api("/v1/chat/completions", {
      method: "POST",
      headers: { "X-Hermes-Session-Id": sid },
      body: JSON.stringify({
        model: "hermes-agent",
        stream: true,
        messages: [...history, { role: "user", content: shown }]
      }),
      signal: controller.signal
    });

    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).error?.message || ""; } catch (e) {}
      throw new Error("HTTP " + res.status + (detail ? " - " + detail : ""));
    }
    ok = true;              // 请求已被接受，用户消息落进会话了
    clearDraft(sid);
    clearDraft(sid0);       // 首轮发送时 sid0 可能还是 null，这里补一刀旧的

    const bubble = addMsg("assistant", "");
    let fullText = "";
    let buf = "";

    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      let idx;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 2);

        let evName = "message", evData = "";
        for (const line of raw.split("\n")) {
          if (line.startsWith("event:")) evName = line.slice(6).trim();
          else if (line.startsWith("data:")) evData += line.slice(5).trim();
        }
        if (!evData || evData === "[DONE]") continue;

        let ev;
        try { ev = JSON.parse(evData); } catch (e) { continue; }

        if (evName === "hermes.tool.progress") {
          if (ev.status === "running") {
            if (!toolCard) toolCard = addToolCard(ev.label || ev.tool || "工具", "");
          } else if (toolCard) {
            toolCard.classList.add("done");
            toolCard.textContent = `✓ ${ev.tool || "工具"}`;
            toolCard = null;
          }
          continue;
        }

        // OpenAI 流式格式：每个 chunk 带 choices[0].delta.content
        const delta = ev.choices && ev.choices[0] && ev.choices[0].delta;
        if (delta && delta.content) {
          fullText += delta.content;
          bubble.textContent = fullText;
          scrollBottom();
        }
      }
    }

    if (!fullText) bubble.textContent = "（无回复）";

    // 首轮对话后把标题补上。
    // 网关要求标题全局唯一，消息前缀很容易重名（连发两次"测试"就撞），
    // 所以重名时追加序号重试。
    const s = sessions.find(x => x.id === sid);
    if (s && !s.title) {
      const base = (text.trim() || "会话").slice(0, 20);
      let title = base;
      for (let n = 1; n <= 9; n++) {
        try {
          const res = await api("/api/sessions/" + encodeURIComponent(sid), {
            method: "PATCH",
            body: JSON.stringify({ title })
          });
          if (res.ok) break;
        } catch (e) { break; }
        title = base + " (" + (n + 1) + ")";
      }
      if (s) s.title = title;
      topbarTitle.textContent = title;
      await loadSessions();
    }

  } catch (err) {
    if (err.name === "AbortError") {
      // 用户主动停止，不提示
    } else if (String(err.message).includes("Failed to fetch")) {
      addMsg("system",
        "无法连接到服务器。\n\n请确认：\n" +
        "1. gateway 是否在运行（双击 start.bat）\n" +
        "2. server.py 代理是否在运行（端口 3000）\n" +
        "3. 手机和电脑是否在同一 WiFi");
    } else {
      addMsg("system", "错误：" + err.message);
    }
  } finally {
    // 没发出去（网络断了/服务器拒了）：文字放回输入框，草稿也留着
    if (!ok) {
      if (!input.value.trim()) input.value = text;
      saveDraft(currentId, input.value);
    }
    controller = null;
    setBusy(false);
    input.focus();
    loadSessions();
  }
}

// ============ 事件绑定 ============
sendBtn.addEventListener("click", () => {
  if (controller) { controller.abort(); return; }
  const text = input.value.trim();
  const names = attachmentNames();
  if (!text && !names.length) return;
  if (!getCfg()) { openCfg(); return; }
  sendMessage(text, names);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    sendBtn.click();
  }
});

input.addEventListener("input", refreshSendState);

// 离开页面（刷新/关标签页）前把输入框内容存成草稿。
// beforeunload 里只能跑同步代码，localStorage.setItem 正好是同步的。
window.addEventListener("beforeunload", () => {
  saveDraft(currentId, input.value);
});

// 手机切后台/切 App 时 beforeunload 常常不触发，用 visibilitychange 补一刀
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") saveDraft(currentId, input.value);
});

newWsBtn.addEventListener("click", createWorkspace);

bindAttachments({
  ensureSession: () => ensureSession(""),
  notify: showError,
});

// 选文件 / 删标签 / 换会话后，发送按钮的可选状态跟着变
attachmentHooks.changed = refreshSendState;
refreshSendState();

toggleBtn.addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
});