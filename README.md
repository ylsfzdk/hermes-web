# Hermes Web Client

一个轻量级的 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 网页客户端，支持流式输出、多工作区会话、任意供应商模型切换、局域网手机访问。

## 功能

- 聊天界面，类似豆包/ChatGPT
- 流式输出（逐字显示）
- 多轮对话记忆
- **左侧栏工作区**：新建 / 切换 / 删除会话，自动以首条消息前 20 字命名
- **切换模型**：选择供应商 → 选择模型 → 填 API Key / API 地址 → 确认，自动改写配置并重启网关
- 供应商按前缀过滤、模型按包含过滤，均为浮层下拉（本机目录 235 家供应商 / 8944 个模型，随 `models_dev_cache.json` 变化）
- 工具调用过程可见（运行中 → ✓ 完成 / ✗ 失败）
- **会话级附件**：输入行左侧 📎 按钮选文件，84 种格式 + 20 MB 上限 + 文件头校验，按会话存到 `<HERMES_HOME>/sessions/<会话ID>/attachments/`
- 生成中可中断（发送按钮变「停止」）
- 输入框没字也没有附件时，发送按钮不可用
- 局域网内手机浏览器直接访问，窄屏自动收起侧栏
- 无需数据库，前端零构建

## 前置要求

1. 已安装 Hermes Agent，要求 **源码启动**：本仓库同级目录 `E:\hermes-agent-0.23.1\`
2. 源码树里有可用的 `.venv\Scripts\python.exe`（它的 site-packages 里没有 hermes 源码，靠 `PYTHONPATH` + cwd 指到源码树才能 import）
3. 数据目录是源码树下的 `.hermes-home\`，在它的 `.env` 里配置（**都在这里配，不要只靠系统环境变量**）：

```
DEEPSEEK_API_KEY=sk-...             # 模型密钥：网关不读 User/系统环境变量，只读这个文件
DEEPSEEK_BASE_URL=https://api.deepseek.com
API_SERVER_ENABLED=true
API_SERVER_KEY=<16 位以上的随机串>    # 网页端要填的同一个值
API_SERVER_HOST=127.0.0.1           # 只给本机网页服务器代理用
```

> 踩过的坑：`DEEPSEEK_API_KEY` 只放在 Windows 用户环境变量里时，`hermes` 报 `No usable credentials found for provider 'deepseek'`，网页端表现为回复「couldn't connect to the AI model service」。写进 `.hermes-home\.env` 才生效。
>
> 源码树路径默认由 `backend\config_paths.py` 按 `..\hermes-agent-0.23.1` 算出来（`HERMES_SRC`），数据目录是 `HERMES_HOME`（默认 `<源码树>\.hermes-home`）。源码树搬家时改 `HERMES_SRC` 环境变量或那一行常量即可，所有模块跟着走。**`HERMES_SRC` 和 `HERMES_HOME` 是两个独立变量**：只改前者会让数据目录跟着漂到新源码树下，原来的会话和 `.env` 就找不到了。
>
> 网关通过 **PATH 上的 `hermes.exe`** 启动（`backend\launch_gateway.py` 调用 `hermes gateway run`），所以 `E:\hermes-agent-0.23.1\.venv\Scripts` 必须在 PATH 里。`cwd` 和 `PYTHONPATH` 仍由代码设到源码树，不依赖 PATH。
>
> 踩过的坑：PATH 上的 `hermes.exe` 若来自别的 pip 安装，会静默连到另一个数据目录。确认 `where hermes` 指向 `.venv\Scripts`。

> 同源代理改造后**不再需要** `API_SERVER_CORS_ORIGINS`——页面和网关都通过 3000 端口，不存在跨域。

## 快速启动

双击 `start.bat`：

1. 用 `..\hermes-agent-0.23.1\.venv\Scripts\python.exe` 启动 `backend\server.py`
2. `launch_gateway.ensure()`：8642 已有网关就复用，没有就通过 PATH 上的 `hermes gateway run` 拉起，最多等 10 秒（冷启动实测 20–60 秒，等不到也照样往下走，网关在后台继续起）
3. 网页服务监听 3000

然后浏览器打开 http://localhost:3000

启动后第一次打开页面会弹窗要求填写 `API_SERVER_KEY`，填写后保存在浏览器 localStorage，不会上传。

### 网关的生命周期

- **退出时**只关本进程拉起的那个网关（`terminate()`，Windows 上是硬杀）
- **代理失败时**（`/api/*` 连不上 8642）自动重新拉起一次
- **网关重启中**（切模型 / 切推理档位触发）发消息的请求会在代理层挂起等待，最多 120 秒，而不是立刻 502
- 网关空闲 10 分钟会自行退出（Hermes 的 `gateway.unmanaged_idle_exit_seconds`），下次请求会自动拉起
- 状态查询：`GET /_gateway_status` → `{ ok, restarting, up }`

## 手机访问

1. 确保手机和电脑连同一个 WiFi
2. `start.bat` 启动时会打印局域网地址，形如 `Phone access: http://192.168.x.x:3000`
3. 手机浏览器打开该地址即可

## 目录结构

```
E:\hermes-web\
├── frontend\
│   ├── index.html            页面骨架（CSS 和 JS 都外链）
│   ├── css\
│   │   ├── base.css          侧栏 / 主区 / 消息气泡 / 输入框
│   │   ├── dialog.css        弹窗公共：遮罩、卡片、按钮
│   │   ├── key-dialog.css    密钥弹窗
│   │   └── model-dialog.css  模型切换弹窗（含浮层下拉）
│   └── js\
│       ├── main.js           入口：接好各模块后启动
│       ├── common.js         配置读写、遮罩显隐、左下角设置菜单
│       ├── chat.js           会话列表 + 消息渲染 + SSE 流式回复
│       ├── config.js         密钥弹窗
│       ├── attachments.js    会话级附件：📎 选文件、格式/大小校验、上传
│       ├── reasoning.js      推理强度：输入框左边按钮切换档位
│       └── model.js          模型切换弹窗
├── backend\
│   ├── server.py         入口：路由（/_model、/_reasoning、/_gateway_status、/_attachments、代理、静态文件）+ 线程化 HTTP 服务
│   ├── launch_gateway.py 网关进程管理：ensure / restart / stop / wait_ready，通过 PATH 上的 hermes 启动
│   ├── attachments.py    /_attachments 上传/列表/删除：格式白名单 + 文件头探测 + 20 MB 上限
│   ├── proxy.py          /api/、/v1/、/health 反向代理（SSE 逐块转发；网关重启时排队等待）
│   ├── model_api.py      GET/POST /_model 查询与切换模型、POST /_reasoning 切推理档位（改完即重启网关）
│   ├── hermes_config.py  读写 <HERMES_HOME>\config.yaml 与模型缓存
│   └── config_paths.py   路径 / 端口 / 代理前缀常量
├── start.bat     启动器（起网页服务，网关由 server.py 拉起）
├── README.md     本文件
└── .gitignore
```

静态站点根目录是 `frontend\`，`backend\` 里的 `*.py` 不会被网页暴露。

前端是**零构建**的原生 ES module：浏览器直接 `import`，没有打包步骤。代价是必须通过 `start.bat`（或 `python backend\server.py`）访问，直接双击 `index.html` 打开 `file://` 会因为跨域限制加载不了模块。

## 端口

| 端口 | 用途 |
|---|---|
| 3000 | 网页 + 同源反向代理（必须是 `backend\server.py`，用 `python -m http.server 3000` 会导致 `/api/*` 全部 404） |
| 8642 | Hermes Gateway（`server.py` 把 `/api/`、`/v1/`、`/health` 转发到这里） |

## 附件（会话级）

输入行下面那一行最左边是 📎 按钮，选中的文件先过基础校验，通过才落盘。

```
┌──────────────────────────────────────────┐
│  跟 Hermes 说点什么...                    │
│  [📎]                  [默认]  [ 发送 ]   │
└──────────────────────────────────────────┘
```

### 校验规则

| 项 | 规则 |
|---|---|
| 格式 | 84 种扩展名：文档 / 表格 / 演示 / 图片 / 代码 / 纯文本 / 配置，白名单在 `backend\attachments.py` 的 `TYPES` |
| 大小 | 单文件 ≤ 20 MB，前后端各拦一次 |
| 真实格式 | PDF、PNG、JPEG、GIF、WebP、TIFF、BMP、ICO、HEIC、AVIF、Office 老格式（OLE2）和新格式（ZIP 容器）会读文件头，改后缀蒙混的直接拒 |
| 空文件 | 拒绝 |

前端在选文件时先挡一遍（扩展名 + 大小），后端以实际收到的字节数为准再验一次，并做文件头探测。

### 落盘时机

**选文件只预检，点「发送」才真正写盘。** 预检走 `POST /_attachments?session_id=xxx&commit=0`，只校验不落盘。

代价：还没发送的附件只存在浏览器内存里，刷新页面或切换会话就没了。

### 存放位置

与会话 ID 绑定，和 Hermes 自己的会话数据放在一起：

```
<HERMES_HOME>/sessions/<会话ID>/
├── attachments/
│   ├── index.json           元数据数组（原名 / 类型 / 大小 / 随机存储名 / 时间 / sent）
│   └── <随机名>.<ext>       文件本体（存储名不跟原名走，避免路径注入和同名覆盖）
└── ...                      该会话目录下的其他文件
```

### 删除会话时的清理范围

> ⚠️ **会话和附件之间没有外键**，只靠目录名里的会话 ID 对齐。网关的 `DELETE /api/sessions/{id}` **只删 `state.db` 里的记录，不碰这个目录**。

所以前端删会话时会额外调 `DELETE /_attachments?session_id=<会话ID>`，把**整个 `sessions/<会话ID>/` 目录**删掉——附件和该目录下的其他文件一起清。

**不删**：

- `sessions/` 根目录下的 `request_dump_*.json`（网关写的失败请求快照，含完整请求体，暂保留）
- `sessions/saved/`（主动导出的会话存档，不属于运行时数据）

直接调网关 API 删会话、不经过网页的话，目录仍会残留，需要手动清理。

### 发送与刷新

- 发送时消息前会拼上 `[附件] 文件名`，**只传文件名不传内容** —— 模型需要自己用工具去读磁盘上的文件（所以聊天里可能会看到 `✓ terminal`）
- 发送成功后输入框上的文件标签会清空，后端把附件标记为 `sent`
- 刷新页面只恢复「还没发出去」的标签；已发送的不会再冒出来

自检：`python backend\attachments.py`（84 种格式 + 落盘删除闭环）。

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

1. 改写 `<HERMES_HOME>/config.yaml` 的 `model:` 段（`provider` / `name` / `default` / `api_key` / `base_url`），原文件备份为 `config.yaml.bak`
2. 把选中的供应商写回 `<HERMES_HOME>/provider_models_cache.json`
3. 杀掉当前网关进程，后台线程用 `hermes gateway run` 重新拉起（冷启动 20–60 秒，接口不阻塞等待）

模型与供应商都没变、也没填 Key / 地址时，「确认」直接关闭面板，不重启网关。

> **注意**：供应商列表来自 `<HERMES_HOME>/models_dev_cache.json`（只读）。切到没配置过 key 的供应商时，必须同时填 API Key 和 API 地址，否则会鉴权失败。
>
> **重启失败不会自动回滚**：配置已经写进去了，`.bak` 留着手动还原。重启期间发消息的请求会在代理层挂起等待，最多 120 秒。

## 后端接口

`server.py` 额外提供以下接口（不属于 Hermes 原生 API）：`/_model`、`/_reasoning`、`/_gateway_status`、`/_attachments`。

### `GET /_model`

返回当前模型、全部供应商、以及每家供应商的模型列表。

```json
{
  "provider": "deepseek",
  "current": "deepseek-flash",
  "base_url": "https://api.deepseek.com/v1",
  "has_key": true,
  "available": ["deepseek-v4-pro", "deepseek-flash", "..."],
  "providers": ["302ai", "abacus", "...共 235 家..."],
  "catalog": { "deepseek": ["deepseek-flash", "..."], "...": [] }
}
```

`base_url` / `has_key` 直接读自 `config.yaml` 的 `model:` 段；`has_key` 只表示是否已配密钥，不回传明文。

### `POST /_model`

```json
{ "model": "deepseek-v4-pro", "provider": "deepseek",
  "api_key": "sk-...", "base_url": "https://api.deepseek.com/v1" }
```

`api_key` / `base_url` 可省略（省略则不改）。

成功返回 `{ "ok": true, "model", "provider", "backup" }`；网关起不来时返回 `{ "ok": false, "warning", "backup" }`，HTTP 状态码仍是 200，前端以 `ok` 判断。**配置不回滚**，需要时手动用 `config.yaml.bak` 还原。

### `GET /_gateway_status`

```json
{ "ok": true, "restarting": false, "up": true }
```

`restarting` 为真表示网关正在重启（切模型 / 切推理档位触发）；`up` 表示 8642 端口可连。

### `GET /_attachments?session_id=<会话ID>`

列出该会话的全部附件。

```json
{
  "ok": true,
  "files": [
    { "name": "报告.pdf", "ext": "pdf", "type": "PDF", "size": 14,
      "id": "192e183a2cee", "stored": "d2874ac05c13b083.pdf",
      "ts": 1794059460, "sent": false }
  ]
}
```

### `POST /_attachments?session_id=<会话ID>`

上传并落盘，`multipart/form-data`，字段名 `file`。

在 query 后加 `&commit=0` 则**只校验不落盘**，成功返回 `{ "ok": true, "file": { name, ext, type, size } }`（没有 `id` / `stored`）。

校验失败返回 400，`{ "error": "不支持的文件格式：.exe" }` 或 `{ "error": "文件内容与扩展名 .png 不符，已拒绝" }`。

### `POST /_attachments/sent?session_id=<会话ID>`

把已随消息发出的附件标记为 `sent`，体 `{ "ids": ["..."] }`。标记后刷新页面不会再把它们当成待发附件恢复。

### `DELETE /_attachments/<附件id>?session_id=<会话ID>`

删单个附件（文件 + 元数据）。不存在返回 404。

### `DELETE /_attachments?session_id=<会话ID>`

**删除整个 `sessions/<会话ID>/` 目录**，包括 `attachments/` 和该目录下的其他文件。前端删会话时自动调用。

- 幂等：目录不存在也返回 200，`{ "ok": true, "removed": false }`
- **不动** `sessions/` 根目录下的 `request_dump_*.json`，也不动 `sessions/saved/`
- `session_id` 会做格式校验（只允许 `A-Za-z0-9_.:-`），删除前用 `realpath` 确认目标是 `sessions/` 下正好一层、名字等于会话 ID 的目录，防路径穿越

## 推理强度

Hermes 原生支持 `/reasoning` 命令（`agent.reasoning_effort`），但这是**网关全局配置**，不是单轮参数：
`/api/sessions/{id}/chat/stream` 不接收 reasoning 字段，每次请求都由 `_create_agent` 读 `config.yaml`。

左下角 **⚙ 设置 → 推理强度** 点一下循环切档：`默认 → none → minimal → low → medium → high → xhigh → 默认`。

- 改的是 `<HERMES_HOME>/config.yaml` 的 `agent.reasoning_effort`，先备份成 `.bak`，再重启网关（对话会中断）
- 值没变则不写文件、不重启
- `默认` 是不设该键，由 Hermes/供应商自己决定（DeepSeek 官方端默认 `high`）
- DeepSeek 实际映射：`low` / `medium` / `high` 原样传 `reasoning_effort`，`xhigh` → `max`；
  `none` 关 thinking；`minimal` 会被 Hermes 丢掉（DeepSeek 无该档）
- 非 DeepSeek 供应商的映射走各自的 provider profile，未注册的供应商可能不生效

对应接口 `POST /_reasoning`：`{ "level": "high" }`，非法档位返回 400。改完立即重启网关，重启期间发消息会挂起等待。

## 已知限制

- **`/_model`、`/_reasoning`、`/_attachments` 无鉴权**：能打开本页面的局域网设备都能改本机模型配置、API Key，或往磁盘写文件，仅限可信网络使用
- **配置不回滚**：切模型 / 切推理档位失败时 `config.yaml` 保持新值，需手动从 `.bak` 还原
- **网关重启期间 `/api/*` 会挂起**：请求在代理层排队最多 120 秒；网关重启失败时表现为"卡住"而不是立即报错
- **网关硬杀不优雅**：`stop()` / `restart()` 在 Windows 上走 `terminate()`（`TerminateProcess`），Hermes 的关库流程来不及跑完
- **跨供应商不自动配 `base_url`**：切到 openrouter 等供应商时，`base_url` 仍停在上一个供应商的值，需手动填写
- **`/_model` 返回约 2MB**：包含全部模型的目录，首次加载稍慢
- **`deepseek-flash` 会被 Hermes 改写为 `deepseek-chat`**：这是 Hermes 的模型名规范化规则，官方 `deepseek-chat` 别名同样指向最新的 V4.1 Flash，实际效果一致，仅日志中显示为别名
- **附件只传文件名，不传内容**：模型拿到的是 `[附件] 文件名`，需要自己用工具去读磁盘上的文件。PDF / Word / Excel 的内容解析尚未实现，白名单只解决"收得下"，不等于"读得懂"
- **附件与会话无外键关联**：删会话的清理只覆盖网页端路径，直接调网关 API 删会话会残留附件目录
- **未发送的附件刷新即丢**：选文件只预检不落盘，文件暂存在浏览器内存
- **旧记录兼容**：`index.json` 里缺 `sent` 字段的历史记录会被当成待发附件，刷新时仍会显示成标签
- **启动只等 10 秒**：`WAIT_SECONDS = 10`，冷启动 20–60 秒时必然判"未就绪"，此时网关在后台继续起，前几十秒页面会 502

## 开发提示

- 修改前端后浏览器需 `Ctrl + Shift + R` 强制刷新，静态文件缓存可能吃掉改动
- 修改 `backend\` 下任何 `.py` 后必须关闭并重开 `start.bat`（当前窗口的 PATH 是旧快照）
- 改过系统 PATH 后必须重开终端，`shutil.which("hermes")` 才找得到新的 `hermes.exe`
- 切换模型后若页面发消息没反应，先看 `GET /_gateway_status` 的 `up`，再看浏览器 Network 里的请求状态码

### 自检

```powershell
# 附件模块自检：格式/大小/文件头校验 + 落盘删除闭环，约 0.2 秒
cd E:\hermes-web\backend; python attachments.py

# 配置读写自检：真实 config.yaml 形状（注释段在前、agent 在 model 前）
cd E:\hermes-web\backend; python hermes_config.py

# 路径自检：源码树 / 数据目录是否对（HERMES_PY 常量已移除，网关走 PATH）
cd E:\hermes-web\backend; python -c "import config_paths as c, shutil; print(c.HERMES_SRC, c.HERMES_DIR, shutil.which('hermes'))"

# 前端语法检查（改完 JS 必跑）
node --check E:\hermes-web\frontend\js\attachments.js
node --check E:\hermes-web\frontend\js\chat.js
```

自检会在 `backend\.attach-selfcheck\` 建临时根，跑完自动删除，不碰真实数据。

### 查看实际使用的模型

问模型"你是什么模型"**不可靠**（模型按训练时的自我认知回答）。看日志才准：

```powershell
Select-String "E:\hermes-agent-0.23.1\.hermes-home\logs\agent.log" -Pattern 'API call #' | Select-Object -Last 5
```

### 查看附件

```powershell
# 列出所有带附件的会话
Get-ChildItem "E:\hermes-agent-0.23.1\.hermes-home\sessions" -Directory |
  Where-Object { Test-Path (Join-Path $_.FullName 'attachments') } |
  ForEach-Object {
    $idx = Join-Path $_.FullName 'attachments\index.json'
    [pscustomobject]@{
      会话ID = $_.Name
      时间   = if (Test-Path $idx) { (Get-Item $idx).LastWriteTime } else { $_.LastWriteTime }
      附件数 = if (Test-Path $idx) { @(Get-Content $idx -Raw | ConvertFrom-Json).Count } else { 0 }
    }
  } | Sort-Object 时间 -Descending | Format-Table -AutoSize
```

## 配置

页面里没有需要手动改的常量。下列内容全部在运行时管理：

| 配置 | 存放位置 |
|---|---|
| 网关密钥 `API_SERVER_KEY` | 浏览器 localStorage（首次打开时填写） |
| 当前模型与供应商 | `<HERMES_HOME>/config.yaml` |
| 会话列表与消息 | `<HERMES_HOME>/state.db`（Hermes Gateway 管理） |
| 附件文件与元数据 | `<HERMES_HOME>/sessions/<会话ID>/attachments/` |
| 当前会话 ID | 浏览器 localStorage（`hermes.currentWs`） |