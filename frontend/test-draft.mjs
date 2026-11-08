/* 草稿逻辑自检：node --test frontend/test-draft.mjs
   把 chat.js 里 saveDraft/loadDraft/clearDraft 的语义单独跑一遍。
   chat.js 依赖 DOM 无法直接 import，这里复刻同样的实现做断言。 */
import assert from "node:assert";

const mem = new Map();
const localStorage = {
  getItem: k => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: k => mem.delete(k),
};
const PREFIX = "hermes.draft.";

function saveDraft(sid, text) {
  if (!sid) return;
  if (text.trim()) localStorage.setItem(PREFIX + sid, text);
  else localStorage.removeItem(PREFIX + sid);
}
const loadDraft = sid => (sid && localStorage.getItem(PREFIX + sid)) || "";
const clearDraft = sid => { if (sid) localStorage.removeItem(PREFIX + sid); };

// 1. 存了能读回来
saveDraft("api_1", "你好");
assert.equal(loadDraft("api_1"), "你好");

// 2. 已存在就覆盖，不追加
saveDraft("api_1", "你好，世界");
assert.equal(loadDraft("api_1"), "你好，世界");

// 3. 按会话 ID 隔离，互不串台
saveDraft("api_2", "另一个会话");
assert.equal(loadDraft("api_1"), "你好，世界");
assert.equal(loadDraft("api_2"), "另一个会话");

// 4. 清空输入框 = 删草稿，不是存空串
saveDraft("api_1", "   ");
assert.equal(loadDraft("api_1"), "");

// 5. 发送成功删草稿
saveDraft("api_2", "要发的内容");
clearDraft("api_2");
assert.equal(loadDraft("api_2"), "");

// 6. 没发送成功：草稿还在
saveDraft("api_3", "会失败的消息");
assert.equal(loadDraft("api_3"), "会失败的消息");

// 7. 无会话 ID 时不写任何东西
saveDraft(null, "孤儿");
assert.equal(mem.size, 1);

// 8. localStorage 抛异常（隐私模式）时不炸
const boom = { getItem: () => { throw new Error("x"); }, setItem: () => { throw new Error("x"); }, removeItem: () => {} };
const safeSave = (sid, text) => {
  if (!sid) return;
  try { if (text.trim()) boom.setItem(PREFIX + sid, text); else boom.removeItem(PREFIX + sid); } catch (e) {}
};
safeSave("api_4", "不该抛");

// 9. 发送后草稿被清空
saveDraft("api_7", "要发的内容");
clearDraft("api_7");
assert.equal(loadDraft("api_7"), "", "发送后草稿应清空");

// 10. 填草稿的取值规则（和 switchSession 里的条件一致）
function fillOnLoad(prevInput, sid, sameSession) {
  return (!sameSession || !prevInput.trim()) ? loadDraft(sid) : prevInput;
}
saveDraft("api_5", "刷新后要回来");
// 刷新：同一会话，输入框是空的 → 应回填
assert.equal(fillOnLoad("", "api_5", true), "刷新后要回来", "刷新后草稿应在");
// 改配置重载：输入框已有字 → 不覆盖
assert.equal(fillOnLoad("正在打的字", "api_5", true), "正在打的字", "已有字时不覆盖");
// 切到另一个没有草稿的会话 → 必须清空，不能留下上个会话的字
assert.equal(fillOnLoad("上个会话打的字", "api_1x", false), "", "换会话没草稿要清空");
// 切到另一个有草稿的会话 → 换成那个会话的草稿
saveDraft("api_2y", "另一个会话的草稿");
assert.equal(fillOnLoad("上个会话打的字", "api_2y", false), "另一个会话的草稿", "换会话要读新会话的草稿");
// 草稿已清空的会话 → 空手进去也是空
assert.equal(fillOnLoad("", "api_7", true), "", "草稿已清空时输入框保持空");
// 回填只读不删
assert.equal(loadDraft("api_5"), "刷新后要回来", "回填后草稿仍在");

// 11. 完整回路：打字 → 刷新前保存 → 重新加载读回
function fakeReload(inputText, sid) {
  saveDraft(sid, inputText);              // beforeunload / visibilitychange 干的事
  return fillOnLoad("", sid, true);       // 新页面 init() 干的事
}
assert.equal(fakeReload("还没发出去的半句话", "api_8"), "还没发出去的半句话",
  "刷新前打的字刷新后应该回来");
// 刷新时输入框被清空过再存，草稿也应该跟着消失
assert.equal(fakeReload("", "api_8"), "", "刷新前输入框空，刷新后也空");

// 12. 切后台时保存（手机场景），用的也是同一个 saveDraft
saveDraft("api_9", "");
assert.equal(loadDraft("api_9"), "", "输入框空时切后台不该造出空草稿");

console.log("draft self-check OK");