/* ============================================================
   公共：对话框显隐、左下角设置菜单、配置读写
   ============================================================ */

export const CFG_KEY = "hermes.cfg";

// 地址固定：同源 + 由 server.py 代理到 8642
export const API_BASE = "";

export function loadCfg() {
  try {
    const c = JSON.parse(localStorage.getItem(CFG_KEY) || "null");
    if (c && c.key) return c;
  } catch (e) {}
  return null;
}

export function saveCfg(c) { localStorage.setItem(CFG_KEY, JSON.stringify(c)); }

export const show = (el) => el.classList.add("show");
export const hide = (el) => el.classList.remove("show");

// ---------- 左下角设置菜单 ----------
const settingsPop = document.getElementById("settings-pop");
const gearBtn = document.getElementById("gear-btn");

export function closeSettings() { hide(settingsPop); }

// 只存函数，避免与 config.js 循环依赖（两边互相 import 会触发 TDZ）
const openers = { cfg: null, model: null };

export function registerOpeners(cfgOpen, modelOpen) {
  openers.cfg = cfgOpen;
  openers.model = modelOpen;
}

export function toggleSettings() {
  if (settingsPop.classList.contains("show")) closeSettings();
  else {
    show(settingsPop);
    // 只在第一次打开时拉取，之后靠切换模型成功后刷新
    if (openers.model) openers.model.loadInfo();
  }
}

export function bindSettingsMenu(onModel) {
  gearBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleSettings();
  });

  document.getElementById("row-key").addEventListener("click", () => {
    closeSettings();
    openers.cfg();
  });

  document.getElementById("row-model").addEventListener("click", () => {
    closeSettings();
    onModel();
  });

  // 点空白处关闭菜单
  document.addEventListener("click", (e) => {
    if (!settingsPop.contains(e.target) && e.target !== gearBtn && !gearBtn.contains(e.target)) {
      closeSettings();
    }
  });
}

// 只在配置变化时需要重载页面数据（由 index.html 注入）
export const hooks = { reload: null };