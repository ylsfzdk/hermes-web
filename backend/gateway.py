"""hermes gateway 进程管理：结束占用端口的进程、重启并等待就绪。"""
import os
import socket
import subprocess
import time


def _no_window():
    return 0x08000000 if os.name == "nt" else 0


def kill_port(port=8642):
    """结束占用指定端口的进程（不依赖 hermes gateway stop）。"""
    try:
        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, timeout=10,
            creationflags=_no_window()
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
                           creationflags=_no_window())
        return True
    except Exception:
        return False


def restart(port=8642):
    """重启 hermes gateway（隐藏窗口），返回 (ok, err)。"""
    kill_port(port)
    time.sleep(2)

    try:
        # 用 hermes.exe 的完整路径，避免依赖 PATH 解析
        exe = "hermes"
        subprocess.Popen(
            [exe, "gateway"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_no_window(),
            close_fds=True,
            shell=False,
        )
    except Exception as e:
        return False, str(e)

    # 等端口就绪
    for _ in range(40):
        time.sleep(1)
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=1)
            s.close()
            return True, None
        except Exception:
            continue
    return False, "网关 40 秒内未就绪"