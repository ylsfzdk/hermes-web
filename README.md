# Hermes Web Client

一个轻量级的 Hermes Agent 网页客户端，支持流式输出、局域网手机访问。

## 功能

- 聊天界面，类似豆包/ChatGPT
- 流式输出（逐字显示）
- 多轮对话记忆
- 局域网内手机浏览器直接访问
- 无需数据库，纯前端单文件

## 前置要求

1. 已安装 [Hermes Agent](https://github.com/NousResearch/hermes-agent)
2. 已在 `~/.hermes/.env` 中配置：
API_SERVER_ENABLED=true
API_SERVER_KEY=your-secret-key
API_SERVER_HOST=0.0.0.0
API_SERVER_CORS_ORIGINS=[http://localhost:3000](http://localhost:3000),http:// 你的 IP:3000

3. Python 3.x

## 快速启动

双击 `start.bat`，会自动启动 Hermes Gateway 和网页服务器。

然后浏览器打开 http://localhost:3000

## 手机访问

1. 确保手机和电脑连同一个 WiFi
2. 查看电脑局域网 IP（`ipconfig`）
3. 手机浏览器打开 `http://你的IP:3000`

## 配置

编辑 `index.html`，修改顶部两个常量：

```javascript
const API_URL = "http://你的IP:8642/v1/chat/completions";
const API_KEY = "your-secret-key";
