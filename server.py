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
import re
import json
import subprocess
import time

BACKEND = "http://127.0.0.1:8642"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
ROOT = os.path.dirname(os.path.abspath(__file__))
PROXY_PREFIXES = ("/api/", "/v1/", "/health")

HERMES_DIR = os.path.expanduser("~/.hermes")
CONFIG = os.path.join(HERMES_DIR, "config.yaml")
MODELS_CACHE = os.path.join(HERMES_DIR, "provider_models_cache.json")
MODELS_DEV_CACHE = os.path.join(HERMES_DIR, "models_dev_cache.json")


def _read_config_model():
    """从 config.yaml 读当前模型与供应商。"""
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {"provider": None, "current": None}

    provider = None
    current = None
    inside = False
    for line in text.splitlines():
        if line.startswith("model:"):
            inside = True
            continue
        if inside:
            if line.strip() and not line[0].isspace():
                break
            s = line.strip()
            if s.startswith("provider:") and provider is None:
                provider = s.split(":", 1)[1].strip() or None
            elif s.startswith("default:") and current is None:
                current = s.split(":", 1)[1].strip() or None
    return {"provider": provider, "current": current}


def _catalog():
    """models.dev 全量目录 {provider: {model_id: 规格}}，只读。"""
    try:
        with open(MODELS_DEV_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _list_models(provider):
    """读 provider 的候选模型（本地缓存优先，缺的从 models.dev 全量目录补齐）。"""
    models = []
    try:
        with open(MODELS_CACHE, "r", encoding="utf-8") as f:
            models = list(json.load(f).get(provider, {}).get("models", []))
    except Exception:
        pass
    models += [m for m in _catalog().get(provider, {}).get("models", {}) if m not in models]
    return models


def _providers():
    """全量供应商（来自 models.dev 目录，只读）。"""
    return sorted(p for p, v in _catalog().items() if v.get("models"))


def _cache_provider(provider, models):
    """把用户选中的供应商连同模型写进 provider_models_cache.json。

    只增改这一条，其他供应商和时间戳原样保留。
    """
    try:
        with open(MODELS_CACHE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    entry = cache.setdefault(provider, {})
    entry["models"] = list(models)
    entry["at"] = time.time()
    entry.setdefault("fp", "")
    tmp = MODELS_CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MODELS_CACHE)


def _write_config_model(new_model, provider=None, base_url=None, api_key=None):
    """把 config.yaml 里 model 段下的 default: 改成 new_model；
    给了 provider / base_url / api_key 就一并改。

    逐行扫描，不用正则——正则版在 11KB 文件上会灾难性回溯。
    """
    with open(CONFIG, "r", encoding="utf-8") as f:
        lines = f.readlines()

    inside_model = False
    changed = False
    seen_provider = False
    seen_key = False
    provider_at = None  # model 段结束前最后一个 provider 行的下标
    key_at = None

    for i, line in enumerate(lines):
        if line.startswith("model:"):
            inside_model = True
            continue
        if inside_model:
            # 遇到顶层键（非缩进、非空行）就离开 model 段
            if line.strip() and not line[0].isspace():
                break
            stripped = line.lstrip()
            indent = line[:len(line) - len(stripped)]
            if stripped.startswith("provider:"):
                provider_at = i
                if provider and not seen_provider:
                    lines[i] = indent + "provider: " + provider + "\n"
                    seen_provider = True
                continue
            if stripped.startswith("api_key:"):
                key_at = i
                if api_key and not seen_key:
                    lines[i] = indent + "api_key: " + json.dumps(api_key) + "\n"
                    seen_key = True
                continue
            if stripped.startswith("base_url:") and base_url:
                lines[i] = indent + "base_url: " + base_url + "\n"
                continue
            if stripped.startswith("default:"):
                lines[i] = indent + "default: " + new_model + "\n"
                changed = True
                break

    if not changed:
        raise RuntimeError("config.yaml 的 model 段里没找到 default 字段")

    # hermes 实际取的是 name: 而不是 default:，两个都改，否则切换不生效
    for i, line in enumerate(lines):
        if line.startswith("model:"):
            inside_model = True
            continue
        if inside_model:
            if line.strip() and not line[0].isspace():
                break
            stripped = line.lstrip()
            if stripped.startswith("name:"):
                indent = line[:len(line) - len(stripped)]
                lines[i] = indent + "name: " + new_model + "\n"
                break

    if provider and not seen_provider:
        if provider_at is None:
            raise RuntimeError("config.yaml 的 model 段里没找到 provider 字段")
        lines.insert(provider_at + 1, "  provider: " + provider + "\n")

    if api_key and not seen_key:
        if key_at is None:
            raise RuntimeError("config.yaml 的 model 段里没找到 api_key 字段")
        lines.insert(key_at + 1, "  api_key: " + json.dumps(api_key) + "\n")

    backup = CONFIG + ".bak"
    try:
        with open(backup, "w", encoding="utf-8", newline="") as f:
            f.writelines(lines)
    except Exception:
        pass

    try:
        with open(CONFIG, "w", encoding="utf-8", newline="") as f:
            f.writelines(lines)
    except PermissionError:
        raise RuntimeError("没有权限修改 config.yaml，请用普通用户身份运行 start.bat")
    return backup


def _kill_port(port=8642):
    """结束占用指定端口的进程（不依赖 hermes gateway stop）。"""
    try:
        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, timeout=10,
            creationflags=0x08000000 if os.name == "nt" else 0
        ).stdout.decode("utf-8", "ignore")

        pids = set()
        for line in out.splitlines():
            if (":%d" % port) in line and "LISTENING" in line.upper():
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit():
                        pids.add(pid)

        for pid in pids:
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"],
                           capture_output=True, timeout=10,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        return True
    except Exception:
        return False


def _restart_gateway():
    """重启 hermes gateway（隐藏窗口），返回 (ok, err)。"""
    _kill_port(8642)
    time.sleep(2)

    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    try:
        # 用 hermes.exe 的完整路径，避免依赖 PATH 解析
        exe = "hermes"
        subprocess.Popen(
            [exe, "gateway"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
            shell=False,
        )
    except Exception as e:
        return False, str(e)

    # 等端口就绪
    import socket
    for _ in range(40):
        time.sleep(1)
        try:
            s = socket.create_connection(("127.0.0.1", 8642), timeout=1)
            s.close()
            return True, None
        except Exception:
            continue
    return False, "网关 40 秒内未就绪"


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

    # ---------- 模型管理 ----------
    def _handle_model_get(self):
        info = _read_config_model()
        cur = info.get("provider") or ""
        info["available"] = _list_models(cur)
        catalog = _catalog()
        providers = sorted(p for p, v in catalog.items() if v.get("models"))
        info["providers"] = providers
        info["catalog"] = {p: sorted(catalog[p]["models"]) for p in providers}
        self._json(info)

    def _handle_model_switch(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            new_model = (body.get("model") or "").strip()
            if not new_model:
                return self._json({"error": "缺少 model 字段"}, 400)
            provider = (body.get("provider") or "").strip() or None
            base_url = (body.get("base_url") or "").strip() or None
            api_key = (body.get("api_key") or "").strip() or None

            backup = _write_config_model(new_model, provider, base_url, api_key)
            if provider:
                _cache_provider(provider, _list_models(provider))
            ok, err = _restart_gateway()
            if not ok:
                return self._json({
                    "ok": False,
                    "model": new_model,
                    "warning": "配置已改，但网关重启失败：" + str(err),
                    "backup": backup,
                }, 200)

            return self._json({"ok": True, "model": new_model,
                               "provider": provider, "backup": backup})
        except Exception as e:
            return self._json({"error": str(e)}, 500)

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
        if self.path == "/_model":
            return self._handle_model_get()
        if self._is_proxy():
            return self._proxy("GET")
        super().do_GET()

    def do_POST(self):
        if self.path == "/_model":
            return self._handle_model_switch()
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