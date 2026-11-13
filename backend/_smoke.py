"""自检：代理这条路通不通（网关要自己先起好，本脚本不拉起它）。

    .venv\\Scripts\\python.exe backend\\_smoke.py
"""
import os
import socket
import sys
import urllib.request

from config_paths import HERMES_DIR, HERMES_SRC

fails = []


def _listening(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


if not _listening(8642):
    print("8642 没有监听：先把网关起起来再跑这个自检")
    sys.exit(1)

# 带 API_SERVER_KEY 打一次 /api/sessions，确认鉴权 + 会话接口都正常
probe = (
    "import sys, urllib.request\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, r'%s')\n"
    "from agent.secret_scope import build_profile_secret_scope\n"
    "k = build_profile_secret_scope(Path(r'%s')).get('API_SERVER_KEY', '')\n"
    "assert len(k) >= 16, 'no API_SERVER_KEY in profile .env'\n"
    "r = urllib.request.Request('http://127.0.0.1:8642/api/sessions?limit=1',\n"
    "                           headers={'Authorization': 'Bearer ' + k})\n"
    "print(urllib.request.urlopen(r, timeout=10).status)\n"
) % (HERMES_SRC, HERMES_DIR)

env = dict(os.environ, HERMES_HOME=HERMES_DIR, PYTHONPATH=HERMES_SRC, PYTHONUTF8="1")
rc = __import__("subprocess").run(
    [os.path.join(HERMES_SRC, ".venv", "Scripts", "python.exe"), "-c", probe],
    cwd=HERMES_SRC, env=env, capture_output=True, timeout=120)
out = rc.stdout.decode("utf-8", "replace").strip()
print("api probe: rc=%d out=%s" % (rc.returncode, out),
      rc.stderr.decode("utf-8", "replace").strip()[-300:])
if rc.returncode != 0 or not out.endswith("200"):
    fails.append("authenticated API probe failed")

print("FAILS:", fails or "none")
sys.exit(1 if fails else 0)