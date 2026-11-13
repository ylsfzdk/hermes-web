"""拉起 Hermes 网关（8642）。server.py 在启动时和代理失败时调它。

单独跑也行：python launch_gateway.py
"""
import os
import socket
import subprocess
import sys
import threading
import time

from config_paths import HERMES_DIR, HERMES_PY, HERMES_SRC

PORT = 8642
WAIT_SECONDS = 10          # 冷启动实测 20-60 秒，等不到也算成功（后台还在起）
_CMD = [HERMES_PY, "-m", "hermes_cli.main", "gateway", "run"]

_lock = threading.Lock()   # 代理是多线程，别同时拉起两个网关
_proc = None               # 本进程拉起的网关


def is_up(port=PORT):
    """端口有没有人听。比发 HTTP 请求便宜，够用。"""
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


def _env():
    """网关必须拿到 HERMES_HOME / PYTHONPATH / VIRTUAL_ENV，否则读的是 ~/.hermes 那份配置。"""
    env = dict(os.environ)
    env["HERMES_HOME"] = HERMES_DIR
    env["VIRTUAL_ENV"] = os.path.dirname(os.path.dirname(HERMES_PY))
    env["PYTHONPATH"] = HERMES_SRC
    env["PYTHONUTF8"] = "1"
    return env


def _alive():
    return _proc is not None and _proc.poll() is None


def ensure(label=""):
    """保证网关在跑。返回 True 表示端口已经在听（或马上就要听）。

    三种情况：已经起来 → 直接返回；自己拉的那个还活着只是在冷启动 → 不再拉第二个；
    其余（没拉过 / 拉起来的那个已经退出了）→ 重新拉一个。
    """
    global _proc
    if is_up():
        return True
    with _lock:
        if is_up():                 # 等锁期间可能已经被别的线程拉起来了
            return True
        if _alive():
            return _alive()         # 正在冷启动，别叠进程
        if not os.path.isfile(HERMES_PY):
            print("[gateway] venv python not found: %s" % HERMES_PY, flush=True)
            return False

        # 上一个拉起来的已经死了，先把它的退出码交代清楚，多半就是启动失败的原因
        if _proc is not None:
            print("[gateway] previous gateway exited with code %s, relaunching%s"
                  % (_proc.returncode, (" (%s)" % label) if label else ""), flush=True)
        else:
            print("[gateway] starting%s..." % ((" (%s)" % label) if label else ""), flush=True)
        print("[gateway] %s" % " ".join(_CMD), flush=True)
        print("-" * 60, flush=True)
        try:
            _proc = subprocess.Popen(_CMD, cwd=HERMES_SRC, env=_env())
        except OSError as e:
            print("[gateway] launch failed: %s" % e, flush=True)
            _proc = None
            return False

        print("[gateway] waiting for %d (cold start usually needs 20-60s)..." % PORT, flush=True)
        start = time.time()
        while time.time() - start < WAIT_SECONDS:
            if is_up():
                print("[gateway] ready on %d." % PORT, flush=True)
                return True
            if _proc.poll() is not None:
                print("[gateway] exited with code %s during startup." % _proc.returncode, flush=True)
                return False
            time.sleep(1)
        print("[gateway] %d not open after %ds, still booting in the background - "
              "the page answers 502 until it is up." % (PORT, WAIT_SECONDS), flush=True)
        return True


def stop(timeout=15):
    """只收本进程拉起来的网关；复用来的（pid 不是我们的）不归这里管。"""
    global _proc
    if not _alive():
        _proc = None
        return
    print("[gateway] stopping...", flush=True)
    _proc.terminate()               # Windows 上是 TerminateProcess，来不及走优雅关闭
    try:
        _proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _proc.kill()
    _proc = None
    print("[gateway] stopped.", flush=True)


if __name__ == "__main__":
    ok = ensure()
    if ok and _alive():
        try:
            _proc.wait()
        except KeyboardInterrupt:
            stop()
    sys.exit(0 if ok else 1)