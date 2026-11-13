/* ============================================================
   密钥配置弹窗
   ============================================================ */

import { loadCfg, saveCfg, show, hide, closeSettings, hooks } from "./common.js";

export let cfg = loadCfg();
export const getCfg = () => cfg;

const mask = document.getElementById("cfg-mask");

export function openCfg() {
  document.getElementById("cfg-key").value = (cfg && cfg.key) || "";
  show(mask);
  setTimeout(() => document.getElementById("cfg-key").focus(), 50);
}

function closeCfg() { hide(mask); }

document.getElementById("cfg-save").addEventListener("click", async () => {
  const key = document.getElementById("cfg-key").value.trim();
  if (!key) { alert("请填写密钥"); return; }

  cfg = { key };
  saveCfg(cfg);
  closeCfg();
  closeSettings();
  if (hooks.reload) await hooks.reload();
});

document.getElementById("cfg-cancel").addEventListener("click", closeCfg);

// 新配置存进来后，模块内的 cfg 也要跟着变（其它模块读 getCfg()）
export function setCfg(c) { cfg = c; }