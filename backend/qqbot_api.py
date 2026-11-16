"""GET / POST /_qqbot：读取 / 保存 QQ 机器人配置；GET /_qqbot/log 取网关日志尾巴。

凭据写 <HERMES_HOME>/.env，开关写 config.yaml 的 platforms.qqbot；
有改动就重启网关让新凭据生效（和切模型一样，重启期间请求在代理层排队）。
"""
import json
import os

import hermes_config as cfg
import launch_gateway
from config_paths import HERMES_DIR

LOG_FILE = os.path.join(HERMES_DIR, "logs", "agent.log")


def get(handler):
    handler._json(cfg.read_qqbot())


def log(handler):
    """GET /_qqbot/log?lines=40：agent.log 的尾巴（读不到就给空表）。

    只看日志里跟 QQ / 网关平台有关的行，别的刷屏内容不往页面上倒。
    """
    from urllib.parse import parse_qs, urlparse
    try:
        want = int((parse_qs(urlparse(handler.path).query).get("lines") or ["40"])[0])
    except Exception:
        want = 40
    want = max(1, min(want, 500))
    lines = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-4000:]
        lines = [l.rstrip("\n") for l in tail
                 if "qqbot" in l.lower() or "[QQBot" in l or "platform" in l.lower()]
        lines = lines[-want:]
    except Exception:
        pass
    handler._json({"ok": True, "lines": lines})


def save(handler):
    try:
        n = int(handler.headers.get("Content-Length") or 0)
        body = json.loads(handler.rfile.read(n).decode("utf-8")) if n else {}
        # 只留认识的字段，其余（profile 之类）一律不看
        keys = ("app_id", "client_secret", "enabled", "dm_authorization",
                "allowed_users", "group_allowed_users", "home_channel", "markdown_support")
        settings = {k: body.get(k) for k in keys if k in body}

        if settings.get("enabled") and not cfg.read_qqbot()["has_secret"] \
                and not (settings.get("client_secret") or "").strip():
            return handler._json({"ok": False, "error": "先填 AppSecret 或扫码，才能启用"}, 400)
        if settings.get("dm_authorization") == "allowlist" and not (settings.get("allowed_users") or "").strip():
            return handler._json({"ok": False, "error": "allowlist 模式至少要填一个 OpenID"}, 400)

        changed = cfg.save_qqbot(settings)
        if not changed:
            return handler._json({"ok": True, "changed": False, "restarting": False})

        restarted = launch_gateway.restart(label="save qqbot")
        return handler._json({
            "ok": True,
            "changed": True,
            "restarting": bool(restarted),
            "warning": None if restarted else "配置已写入，但网关重启失败，请手动重开 start.bat",
        })
    except Exception as e:
        handler._json({"ok": False, "error": str(e) or e.__class__.__name__}, 500)