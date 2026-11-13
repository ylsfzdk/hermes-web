"""
Hermes Web 本地服务器：静态文件 + API 反向代理（同源，免 CORS）

用法: python server.py [port]
默认端口 3000，转发到 127.0.0.1:8642；网关交给 launch_gateway.py 拉起
"""
import http.server
import json
import mimetypes
import signal
import socketserver
import sys

import attachments
import launch_gateway
import model_api
import proxy
from config_paths import BACKEND, PROXY_PREFIXES, ROOT

# Windows 上 .js 常被注册成 text/plain，浏览器会拒绝执行模块脚本
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _is_proxy(self):
        return self.path.startswith(PROXY_PREFIXES)

    def _is_attachments(self):
        path = self.path.split("?", 1)[0]
        return path == "/_attachments" or path.startswith("/_attachments/")

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/_model":
            return model_api.get(self)
        if self.path == "/_gateway_status":
            return self._json({"ok": True,
                               "restarting": launch_gateway.is_restarting(),
                               "up": launch_gateway.is_up()})
        if self._is_attachments():
            return attachments.listing(self)
        if self._is_proxy():
            return proxy.proxy(self, "GET")
        super().do_GET()

    def do_POST(self):
        if self.path == "/_model":
            return model_api.switch(self)
        if self.path == "/_reasoning":
            return model_api.reasoning(self)
        if self._is_attachments():
            if self.path.split("?", 1)[0].endswith("/sent"):
                return attachments.sent(self)
            return attachments.upload(self)
        if self._is_proxy():
            return proxy.proxy(self, "POST")
        self.send_error(404)

    def do_DELETE(self):
        if self._is_attachments():
            # 裸 /_attachments?session_id=xxx 是"删整个会话的附件目录"
            if self.path.split("?", 1)[0].rstrip("/") == "/_attachments":
                return attachments.purge(self)
            return attachments.delete(self)
        if self._is_proxy():
            return proxy.proxy(self, "DELETE")
        self.send_error(404)

    def do_PATCH(self):
        if self._is_proxy():
            return proxy.proxy(self, "PATCH")
        self.send_error(404)

    def do_OPTIONS(self):
        if self._is_proxy():
            return proxy.proxy(self, "OPTIONS")
        self.send_response(204)
        self.end_headers()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        """浏览器主动断开（点停止、关闭标签）是正常现象，打一行就够，不刷 traceback。"""
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            sys.stderr.write("%s - client disconnected\n" % (client_address[0],))
            return
        super().handle_error(request, client_address)


def _on_signal(signum, frame):
    """SIGTERM / Ctrl+Break 也走正常退出路径。"""
    raise KeyboardInterrupt


if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")

    signal.signal(signal.SIGTERM, _on_signal)

    # 起网关（8642 已有监听就复用）。网关的输出直接继承这个窗口。
    # 起不来的话 proxy 每次收到 /api/* 还会再调一次 launch_gateway.ensure() 重试。
    launch_gateway.ensure(label="startup")

    try:
        with ThreadingServer(("", PORT), Handler) as httpd:
            print("Serving on port %d  ->  %s" % (PORT, BACKEND))
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nStopped.")
            finally:
                httpd.server_close()
    finally:
        launch_gateway.stop()