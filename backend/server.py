"""
Hermes Web 本地服务器：静态文件 + API 反向代理（同源，免 CORS）

用法: python server.py [port]
默认端口 3000，转发到 127.0.0.1:8642
"""
import http.server
import json
import mimetypes
import socketserver
import sys

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
        if self._is_proxy():
            return proxy.proxy(self, "GET")
        super().do_GET()

    def do_POST(self):
        if self.path == "/_model":
            return model_api.switch(self)
        if self._is_proxy():
            return proxy.proxy(self, "POST")
        self.send_error(404)

    def do_DELETE(self):
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


if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    with ThreadingServer(("", PORT), Handler) as httpd:
        print("Serving on port %d  ->  %s" % (PORT, BACKEND))
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")