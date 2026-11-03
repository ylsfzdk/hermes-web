"""
Hermes Web 本地服务器：静态文件 + API 反向代理（同源，免 CORS）

用法: python server.py [port]
默认端口 3000，转发到 127.0.0.1:8642
"""
import http.server
import socketserver
import urllib.request
import urllib.error
import os
import sys

BACKEND = "http://127.0.0.1:8642"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
ROOT = os.path.dirname(os.path.abspath(__file__))
PROXY_PREFIXES = ("/api/", "/v1/", "/health")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _is_proxy(self):
        return self.path.startswith(PROXY_PREFIXES)

    def _proxy(self, method):
        url = BACKEND + self.path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "connection", "accept-encoding", "origin")}

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            resp = e
        except Exception as e:
            self.send_error(502, "proxy error: %s" % e)
            return

        try:
            self.send_response(resp.status if hasattr(resp, "status") else resp.code)
            for k, v in resp.headers.items():
                if k.lower() in ("transfer-encoding", "connection", "content-length", "content-encoding"):
                    continue
                self.send_header(k, v)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            # 逐块转发，SSE 不会被缓冲
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def do_GET(self):
        if self._is_proxy():
            return self._proxy("GET")
        super().do_GET()

    def do_POST(self):
        if self._is_proxy():
            return self._proxy("POST")
        self.send_error(404)

    def do_DELETE(self):
        if self._is_proxy():
            return self._proxy("DELETE")
        self.send_error(404)

    def do_PATCH(self):
        if self._is_proxy():
            return self._proxy("PATCH")
        self.send_error(404)

    def do_OPTIONS(self):
        if self._is_proxy():
            return self._proxy("OPTIONS")
        self.send_response(204)
        self.end_headers()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    with ThreadingServer(("", PORT), Handler) as httpd:
        print("Serving on port %d  ->  %s" % (PORT, BACKEND))
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")