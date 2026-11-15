"""同源反向代理：把 /api/、/v1/、/health 转发给 Hermes Gateway。

8642 连不上时调 launch_gateway.ensure() 把网关拉起来；请求本身照样返回 502。
"""
import urllib.error
import urllib.request

import launch_gateway
from config_paths import BACKEND


def _send_plain(handler, code, text):
    """写一个 UTF-8 的纯文本错误响应，状态行只带标准短语。"""
    body = text.encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def proxy(handler, method):
    """在 handler 上把当前请求转发到 BACKEND，逐块回写（SSE 不被缓冲）。"""
    url = BACKEND + handler.path
    length = int(handler.headers.get("Content-Length") or 0)
    body = handler.rfile.read(length) if length else None

    headers = {k: v for k, v in handler.headers.items()
               if k.lower() not in ("host", "connection", "accept-encoding", "origin")}

    # 网关正在重启（切模型 / 切推理档位）：请求先在这里排队，等它回来再转发，
    # 而不是立刻 502 让客户端断开。重启通常 20-60 秒，最多等 120 秒。
    if launch_gateway.is_restarting():
        print("[proxy] gateway restarting, holding %s %s" % (method, url), flush=True)
        launch_gateway.wait_ready(120)

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=300)
    except urllib.error.HTTPError as e:
        resp = e
    except Exception as e:
        # 连不上：网关挂了或没起，拉一个（可能已在冷启动，ensure 自己会去重）
        if not launch_gateway.is_up():
            launch_gateway.ensure(label="proxy %s %s" % (method, handler.path.split("?")[0]))
        # 不能走 send_error：它把 message 塞进 HTTP 状态行再按 latin-1 编码，
        # 而 Windows 的 OSError 提示是中文（"由于目标计算机积极拒绝"），
        # UnicodeEncodeError 会让连 502 都发不出去，浏览器只看到 ERR_EMPTY_RESPONSE。
        _send_plain(handler, 502, "proxy error: %s" % e)
        return

    try:
        handler.send_response(resp.status if hasattr(resp, "status") else resp.code)
        for k, v in resp.headers.items():
            if k.lower() in ("transfer-encoding", "connection", "content-length", "content-encoding"):
                continue
            handler.send_header(k, v)
        handler.send_header("Cache-Control", "no-cache")
        handler.end_headers()

        while True:
            chunk = resp.read(1024)
            if not chunk:
                break
            handler.wfile.write(chunk)
            handler.wfile.flush()
    finally:
        try:
            resp.close()
        except Exception:
            pass