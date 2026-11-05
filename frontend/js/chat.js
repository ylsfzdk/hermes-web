/* ============================================================
   聊天主逻辑：会话列表、消息渲染、SSE 流式回复
   ============================================================ */

import { API_BASE } from "./common.js";
import { getCfg } from "./config.js";
import { openCfg } from "./config.js";

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
  if (id === currentId) {
    currentId = null;
    localStorage.removeItem(CUR_WS);
    chatInner.innerHTML = "";
    topbarTitle.textContent = "Hermes Web";
  }
  await loadSessions();
}

// ============ 切换 / 新建会话 ============
export async function switchSession(id) {
  if (controller) { controller.abort(); controller = null; }
  currentId = id;
  localStorage.setItem(CUR_WS, id);
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
function setBusy(busy) {
  if (busy) {
    sendBtn.textContent = "停止";
    sendBtn.classList.add("stop");
    sendBtn.disabled = false;
  } else {
    sendBtn.textContent = "发送";
    sendBtn.classList.remove("stop");
    sendBtn.disabled = false;
  }
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

async function sendMessage(text) {
  addMsg("user", text);
  input.value = "";
  setBusy(true);

  let toolCard = null;

  try {
    const sid = await ensureSession(text);

    controller = new AbortController();
    const res = await api(`/api/sessions/${encodeURIComponent(sid)}/chat/stream`, {
      method: "POST",
      body: JSON.stringify({ message: text }),
      signal: controller.signal
    });

    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).error?.message || ""; } catch (e) {}
      throw new Error("HTTP " + res.status + (detail ? " - " + detail : ""));
    }

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
        if (!evData) continue;

        let ev;
        try { ev = JSON.parse(evData); } catch (e) { continue; }

        if (evName === "assistant.delta" && ev.delta) {
          fullText += ev.delta;
          bubble.textContent = fullText;
          scrollBottom();
        } else if (evName === "tool.started") {
          if (!toolCard) toolCard = addToolCard("正在调用 " + (ev.tool_name || "工具"), ev.preview);
        } else if (evName === "tool.completed") {
          if (toolCard) { toolCard.classList.add("done"); toolCard.textContent = `✓ ${ev.tool_name || "工具"}`; toolCard = null; }
        } else if (evName === "tool.failed") {
          if (toolCard) { toolCard.classList.add("fail"); toolCard.textContent = `✗ ${ev.tool_name || "工具"} 失败`; toolCard = null; }
        } else if (evName === "assistant.completed" && ev.content) {
          if (ev.content !== fullText) { fullText = ev.content; bubble.textContent = fullText; }
        } else if (evName === "error") {
          throw new Error(ev.message || "服务器错误");
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
      addMsg("system", "已停止生成");
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
  if (!text) return;
  if (!getCfg()) { openCfg(); return; }
  sendMessage(text);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    sendBtn.click();
  }
});

newWsBtn.addEventListener("click", createWorkspace);

toggleBtn.addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
});