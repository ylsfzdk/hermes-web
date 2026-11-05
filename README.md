# Hermes Web Client

一个轻量级的 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 网页客户端，支持流式输出、多工作区会话、任意供应商模型切换、局域网手机访问。

## 功能

- 聊天界面，类似豆包/ChatGPT
- 流式输出（逐字显示）
- 多轮对话记忆
- **左侧栏工作区**：新建 / 切换 / 删除会话，自动以首条消息前 20 字命名
- **切换模型**：选择供应商 → 选择模型 → 填 API Key / API 地址 → 确认，自动改写配置并重启网关
- 供应商与模型均为浮层下拉，支持输入前缀过滤（供应商 235 家、模型 8932 个全量可选）
- 工具调用过程可见
- 生成中可中断（停止按钮）
- 局域网内手机浏览器直接访问
- 无需数据库，纯前端单文件

## 前置要求

1. 已安装 Hermes Agent（`pip install hermes-agent`）
2. 已在 `~/.hermes/.env` 中配置：

```
API_SERVER_ENABLED=true
API_SERVER_KEY=your-secret-key
API_SERVER_HOST=0.0.0.0
```

3. Python 3.x

> 同源代理改造后**不再需要** `API_SERVER_CORS_ORIGINS`——页面和网关都通过 3000 端口，不存在跨域。

## 快速启动

双击 `start.bat`，会自动启动 Hermes Gateway（若未运行）和网页服务器。

然后浏览器打开 http://localhost:3000

启动后第一次打开页面会弹窗要求填写 `API_SERVER_KEY`，填写后保存在浏览器 localStorage，不会上传。

## 手机访问

1. 确保手机和电脑连同一个 WiFi
2. `start.bat` 启动时会打印局域网地址，形如 `Phone access: http://192.168.x.x:3000`
3. 手机浏览器打开该地址即可

## 目录结构

```
E:\hermes-web\
├── index.html    前端单文件（侧栏 / 聊天 / 设置 / 模型切换面板）
├── server.py     静态文件 + 反向代理 + /_model 模型管理接口
├── start.bat     启动器（拉网关 + 起网页服务）
├── README.md     本文件
└── .gitignore
```

## 端口

| 端口 | 用途 |
|---|---|
| 3000 | 网页 + 同源反向代理（必须是 `server.py`，用 `python -m http.server 3000` 会导致 `/api/*` 全部 404） |
| 8642 | Hermes Gateway（`server.py` 把 `/api/`、`/v1/`、`/health` 转发到这里） |

## 切换模型

左下角 **⚙ 设置 → 模型** 打开切换面板：

```
供应商    [输入框 + ▼]   ← 输入名称筛选，或点箭头展开全部 235 家
模型      [输入框 + ▼]   ← 随供应商变化，当前模型标 "✓ 当前"
API Key   [密码框]       ← 留空则沿用供应商已保存的密钥
API 地址  [文本框]       ← 留空则不修改
[确认]  [取消]
```

点「确认」后依次执行：

1. 改写 `~/.hermes/config.yaml` 的 `model:` 段（`provider` / `name` / `default` / `api_key` / `base_url`），原文件备份为 `config.yaml.bak`
2. 把选中的供应商写回 `~/.hermes/provider_models_cache.json`
3. 结束占用 8642 端口的进程并重启网关，约需 3 秒，期间对话会短暂中断

> **注意**：供应商列表来自 `~/.hermes/models_dev_cache.json`（只读）。切到没配置过 key 的供应商时，必须同时填 API Key 和 API 地址，否则会鉴权失败。

## 后端接口

`server.py` 额外提供两个接口（不属于 Hermes 原生 API）：

### `GET /_model`

返回当前模型、全部供应商、以及每家供应商的模型列表。

```json
{
  "provider": "deepseek",
  "current": "deepseek-flash",
  "available": ["deepseek-v4-pro", "deepseek-flash", "..."],
  "providers": ["302ai", "abacus", "...共 235 家..."],
  "catalog": { "deepseek": ["deepseek-flash", "..."], "...": [] }
}
```

### `POST /_model`

```json
{ "model": "deepseek-v4-pro", "provider": "deepseek",
  "api_key": "sk-...", "base_url": "https://api.deepseek.com/v1" }
```

`api_key` / `base_url` 可省略（省略则不改）。

## 已知限制

- **`/_model` 无鉴权**：能打开本页面的局域网设备都能改本机模型配置和 API Key，仅限可信网络使用
- **切换失败不回滚**：配置已写入但网关起不来时，需要手动还原 `config.yaml.bak`
- **跨供应商不自动配 `base_url`**：切到 openrouter 等供应商时，`base_url` 仍停在上一个供应商的值，需手动填写
- **`/_model` 返回约 2MB**：包含全部 8932 个模型的目录，首次加载稍慢
- **`deepseek-flash` 会被 Hermes 改写为 `deepseek-chat`**：这是 Hermes 的模型名规范化规则，官方 `deepseek-chat` 别名同样指向最新的 V4.1 Flash，实际效果一致，仅日志中显示为别名

## 开发提示

- 修改前端后浏览器需 `Ctrl + F5` 强制刷新，静态文件缓存可能吃掉改动
- 修改 `server.py` 后必须关闭并重开 `start.bat`
- 切换模型后若页面发消息没反应，优先看浏览器控制台 Network 里的 `chat/stream` 请求状态码

### 查看实际使用的模型

问模型"你是什么模型"**不可靠**（模型按训练时的自我认知回答）。看日志才准：

```powershell
Select-String "$env:USERPROFILE\.hermes\logs\agent.log" -Pattern 'API call #' | Select-Object -Last 5
```

## 配置

页面里没有需要手动改的常量。下列内容全部在运行时管理：

| 配置 | 存放位置 |
|---|---|
| 网关密钥 `API_SERVER_KEY` | 浏览器 localStorage（首次打开时填写） |
| 当前模型与供应商 | `~/.hermes/config.yaml` |
| 会话列表 | Hermes Gateway 的会话存储 |