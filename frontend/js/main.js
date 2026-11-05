/* ============================================================
   入口：把各模块接起来，然后启动
   ============================================================ */

import { bindSettingsMenu, hooks as settingsHooks } from "./common.js";
import * as chat from "./chat.js";
import { getCfg, openCfg } from "./config.js";
import { loadModelInfo, openModelPicker, hooks as modelHooks } from "./model.js";

const sidebar = document.getElementById("sidebar");

// 配置改动 / 模型切换后重新拉一遍会话和当前会话
const reload = async () => {
  await chat.loadSessions();
  const id = chat.getCurrentId();
  if (id) await chat.switchSession(id);
};

modelHooks.notify = chat.showError;
modelHooks.reload = reload;
settingsHooks.reload = reload;

bindSettingsMenu(openModelPicker);

// ============ 启动 ============
(async function init() {
  if (window.innerWidth <= 720) sidebar.classList.add("collapsed");
  loadModelInfo();
  if (!getCfg()) { openCfg(); return; }
  await reload();
})();