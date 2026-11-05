/* ============================================================
   推理强度：输入框左边的按钮，点开上拉框选档位
   档位存 ~/.hermes/config.yaml 的 agent.reasoning_effort，
   改完要重启网关才生效（和切模型一样，期间对话会中断）
   ============================================================ */

const LABELS = {
  "": "默认",
  none: "关闭",
  minimal: "minimal",
  low: "low",
  medium: "medium",
  high: "high",
  xhigh: "xhigh",
};

const btn = document.getElementById("reasoning-btn");
const nameEl = document.getElementById("reasoning-name");
const pop = document.getElementById("reasoning-pop");

let levels = [""];
let current = "";
let busy = false;
let reloadInfo = null;

function paint() {
  nameEl.textContent = LABELS[current] || current || "默认";
  btn.classList.toggle("on", current !== "");
}

function renderPop() {
  pop.innerHTML = "";
  for (const lv of levels) {
    const d = document.createElement("div");
    d.className = "reasoning-opt" + (lv === current ? " sel" : "");
    d.textContent = (LABELS[lv] || lv) + (lv === current ? "  ✓" : "");
    // mousedown 阻止默认，否则按钮失焦先把框关掉，点不到
    d.addEventListener("mousedown", (e) => e.preventDefault());
    d.addEventListener("click", (e) => {
      e.stopPropagation();
      pop.classList.remove("show");
      if (lv !== current) switchTo(lv);
    });
    pop.appendChild(d);
  }
}

function togglePop() {
  if (pop.classList.contains("show")) {
    pop.classList.remove("show");
    return;
  }
  renderPop();
  pop.classList.add("show");
}

export function renderReasoning(info) {
  if (!info) return;
  if (Array.isArray(info.reasoning_levels) && info.reasoning_levels.length) {
    levels = info.reasoning_levels;
  }
  current = typeof info.reasoning === "string" ? info.reasoning : current;
  paint();
}

export function bindReasoning(reload) {
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    togglePop();
  });
  document.addEventListener("click", (e) => {
    if (!pop.contains(e.target) && !btn.contains(e.target)) {
      pop.classList.remove("show");
    }
  });
  // 选完档位后需要从后端重读一次，绑定在这一层
  reloadInfo = reload;
}

async function switchTo(level) {
  if (busy || level === current) return;
  busy = true;
  nameEl.textContent = "切换中…";
  try {
    const res = await fetch("/_reasoning", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level })
    });
    const json = await res.json();
    if (!json.ok) throw new Error(json.warning || json.error || "切换失败");
    current = level;
    if (reloadInfo) await reloadInfo();
  } catch (e) {
    paint();
  } finally {
    busy = false;
  }
}