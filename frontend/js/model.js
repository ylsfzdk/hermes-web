/* ============================================================
   模型切换弹窗：供应商 / 模型浮层下拉 + 提交切换
   ============================================================ */

import { show, hide } from "./common.js";
import { renderReasoning } from "./reasoning.js";

const mask = document.getElementById("model-mask");
const modelNameEl = document.getElementById("model-name");
const provInput = document.getElementById("model-provider");
const modelInput = document.getElementById("model-select");

let modelInfo = null;
let provCombo, modelCombo;

// 弹窗打开期间，调用方把在页面上提示消息的函数挂进来；不挂就退化成 alert
export const hooks = { notify: null, reload: null };

function notify(msg) {
  if (hooks.notify) hooks.notify(msg);
  else alert(msg);
}

export async function loadModelInfo() {
  try {
    const res = await fetch("/_model", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    modelInfo = await res.json();
    modelNameEl.textContent = modelInfo.current || "未知";
    modelNameEl.classList.remove("warn");
    renderReasoning(modelInfo);
  } catch (e) {
    modelNameEl.textContent = "读取失败";
    modelNameEl.classList.add("warn");
  }
}

function modelNames(provider) {
  if (!modelInfo) return [];
  const same = provider === modelInfo.provider;
  const all = new Set((modelInfo.catalog || {})[provider] || []);
  if (same && modelInfo.current) all.add(modelInfo.current);
  return [...all];
}

function currentModel() {
  const p = provInput.value.trim();
  return modelInfo && p === modelInfo.provider ? modelInfo.current : null;
}

// 供应商变了：重填模型行的候选，并默认选中当前模型或第一个
function renderModelList(provider) {
  const all = modelNames(provider);
  if (!all.length) {
    modelInput.value = "";
    modelInput.placeholder = "该供应商没有可用的模型列表";
    return;
  }
  modelInput.placeholder = "输入名称筛选，或从下拉里选";
  const cur = provider === modelInfo.provider ? modelInfo.current : null;
  modelInput.value = all.includes(cur) ? cur : all[0];
}

export function openModelPicker() {
  const keyEl = document.getElementById("model-key");
  const baseEl = document.getElementById("model-base");
  keyEl.value = "";
  baseEl.value = "";
  // 回填已保存的 base_url；key 不显示明文，只提示是否已配置
  baseEl.value = (modelInfo && modelInfo.base_url) || "";
  keyEl.placeholder = modelInfo && modelInfo.has_key
    ? "已配置，留空则不修改"
    : "输入 API Key";
  document.getElementById("model-confirm").disabled = false;

  if (!modelInfo) {
    provInput.value = "正在读取…";
    loadModelInfo().then(() => openModelPicker());
    show(mask);
    return;
  }

  const providers = modelInfo.providers || [];
  if (!providers.length) {
    provInput.value = "";
    provInput.placeholder = "没有可用的供应商列表";
    show(mask);
    return;
  }

  // 默认停在当前供应商
  provInput.value = modelInfo.provider || "";
  provCombo.render();
  renderModelList(provInput.value);
  show(mask);
}

// ---------- 浮层下拉：供应商和模型共用一套 ----------
const POP_LIMIT = 200;

// state: { input, pop, items: [], active: -1, filter(), onPick(value) }
function makeCombo(input, pop, filter, onPick) {
  // input 点击/聚焦不自动展开，只能由箭头(松开)展开或键盘↓展开
  const st = { input, pop, items: [], active: -1, filter, onPick };

  function showPop(v) { pop.classList.toggle("show", !!v); }
  function render() {
    st.items = filter(input.value.trim());
    st.active = -1;
    pop.innerHTML = "";
    if (!st.items.length) {
      const d = document.createElement("div");
      d.className = "prov-empty";
      d.textContent = "没有匹配项";
      pop.appendChild(d);
      return;
    }
    for (const it of st.items.slice(0, POP_LIMIT)) {
      const d = document.createElement("div");
      d.className = "prov-opt" + (it.cur ? " sel" : "");
      d.textContent = it.label;
      d.dataset.value = it.value;
      // mousedown 阻止默认，保住输入框焦点（否则 blur 先把浮层关掉点不到），
      // 选中动作放在 click 上：这才是"松开鼠标后"才发生
      d.addEventListener("mousedown", (e) => e.preventDefault());
      d.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        onPick(it.value);
        showPop(false);
      });
      pop.appendChild(d);
    }
    if (st.items.length > POP_LIMIT) {
      const d = document.createElement("div");
      d.className = "prov-empty";
      d.textContent = "还有 " + (st.items.length - POP_LIMIT) + " 项，继续输入可缩小范围";
      pop.appendChild(d);
    }
  }
  function move(delta) {
    const opts = [...pop.querySelectorAll(".prov-opt")];
    if (!opts.length) return;
    opts.forEach(o => o.classList.remove("active"));
    st.active = (st.active + delta + opts.length) % opts.length;
    opts[st.active].classList.add("active");
    opts[st.active].scrollIntoView({ block: "nearest" });
  }
  function open() { render(); showPop(true); }

  // 打字即按前缀过滤并弹出浮层；清空输入则收起
  input.addEventListener("input", () => {
    if (input.value.trim()) open();
    else showPop(false);
  });
  input.addEventListener("focus", () => { if (input.value.trim()) open(); });
  input.addEventListener("blur", () => showPop(false));
  input.addEventListener("keydown", (e) => {
    const isOpen = pop.classList.contains("show");
    if (e.key === "ArrowDown") { e.preventDefault(); if (!isOpen) open(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter" && isOpen && st.active >= 0) {
      e.preventDefault();
      const v = pop.querySelectorAll(".prov-opt")[st.active].dataset.value;
      onPick(v);
      showPop(false);
    } else if (e.key === "Escape") { showPop(false); }
  });

  // 全局兜底：任何地方按下鼠标，若不是在本行内部，就收起浮层
  // （比依赖 blur 可靠——箭头 mousedown 会 preventDefault，blur 不一定触发）
  document.addEventListener("mousedown", (e) => {
    if (!input.parentNode.contains(e.target) && !pop.contains(e.target)) showPop(false);
  });

  return { render, show: showPop, open, pop };
}

// 箭头：按下只置标记，松开(mouseup)才展开/收起。
// 全程 preventDefault，保证输入框不丢焦点、浮层不会因 blur 被立刻关掉。
// 注意：pressed 检查要放在 preventDefault 之后、取 pop 之前，否则
// 按住箭头拖到别处松开时 pressed=false，但仍会走到下面读 combo.pop 崩掉。
function bindArrow(arrow, input, combo, pop) {
  let pressed = false;
  const fire = (e) => {
    if (!pressed) return;
    pressed = false;
    e.preventDefault();
    e.stopPropagation();
    if (pop.classList.contains("show")) {
      combo.show(false);
    } else {
      if (document.activeElement !== input) input.focus();
      combo.open();
    }
  };
  arrow.addEventListener("mousedown", (e) => { e.preventDefault(); pressed = true; });
  arrow.addEventListener("mouseup", fire);
  arrow.addEventListener("pointerup", fire);
  arrow.addEventListener("mouseleave", () => { pressed = false; });
}

async function switchModel(el, name, provider, key, baseUrl) {
  el.textContent = "切换中，请稍候…";

  try {
    const res = await fetch("/_model", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: name,
        provider,
        api_key: key || undefined,
        base_url: baseUrl || undefined
      })
    });
    const json = await res.json();
    if (!json.ok) throw new Error(json.warning || json.error || "切换失败");

    hide(mask);
    await loadModelInfo();
    notify("已切换到模型：" + name + (provider ? "（" + provider + "）" : ""));
    if (hooks.reload) await hooks.reload();
  } catch (e) {
    el.disabled = false;
    alert("切换失败：" + e.message);
  } finally {
    el.textContent = "确认";
  }
}

// ---------- 初始化 ----------
// 供应商行：选中后要填回输入框，再刷新模型行
function setProvider(p) {
  provInput.value = p;
  renderModelList(p);
  modelCombo.show(false);
}

provCombo = makeCombo(
  provInput,
  document.getElementById("provider-pop"),
  (q) => (modelInfo ? modelInfo.providers || [] : [])
    .filter(p => !q || p.toLowerCase().startsWith(q.toLowerCase()))
    .map(p => ({ value: p, label: p, cur: modelInfo && p === modelInfo.provider })),
  setProvider
);

// 模型行：选中后填回输入框
modelCombo = makeCombo(
  modelInput,
  document.getElementById("model-pop"),
  (q) => modelNames(provInput.value.trim())
    .filter(m => !q || m.toLowerCase().includes(q.toLowerCase()))
    .map(m => ({
      value: m,
      label: m + (m === currentModel() ? "  ✓ 当前" : ""),
      cur: m === currentModel()
    })),
  (m) => { modelInput.value = m; }
);

// 供应商输入变化时，若正好等于某个供应商，同步刷新模型行候选
provInput.addEventListener("input", () => {
  const v = provInput.value.trim();
  if (modelInfo && (modelInfo.catalog || {})[v]) renderModelList(v);
});

// 在输入框里按 Enter 只确认选项，不让它触发"确认"按钮
[provInput, modelInput].forEach(el =>
  el.addEventListener("keydown", (e) => { if (e.key === "Enter") e.preventDefault(); }));

// 点遮罩空白处收起两边浮层（点弹窗内部不收起）
mask.addEventListener("click", (e) => {
  if (e.target !== mask) return;
  provCombo.show(false);
  modelCombo.show(false);
});

bindArrow(document.getElementById("provider-arrow"), provInput, provCombo,
          document.getElementById("provider-pop"));
bindArrow(document.getElementById("model-arrow"), modelInput, modelCombo,
          document.getElementById("model-pop"));

document.getElementById("model-confirm").addEventListener("click", (e) => {
  e.preventDefault();
  const btn = e.currentTarget;
  const provider = provInput.value.trim();
  const name = modelInput.value;
  if (!provider) return alert("请先选择供应商");
  if (!(modelInfo.catalog || {})[provider])
    return alert("没有这个供应商：" + provider);
  if (!name) return alert("请先选择模型");
  const key = document.getElementById("model-key").value.trim();
  const baseUrl = document.getElementById("model-base").value.trim();

  // 只要 key 有输入、或 base_url 与已保存的不同，就必须提交，
  // 否则只改这两项会被当成"没变"直接吞掉
  const baseChanged = baseUrl !== ((modelInfo && modelInfo.base_url) || "");
  const already = provider === modelInfo.provider && name === modelInfo.current
                  && !key && !baseChanged;
  if (already) { hide(mask); return; }

  btn.disabled = true;
  switchModel(btn, name, provider, key, baseUrl);
});

document.getElementById("model-cancel").addEventListener("click", () => hide(mask));