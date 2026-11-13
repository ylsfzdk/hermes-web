"""GET / POST /_model：查询和切换当前模型。

改完 config.yaml 就重启网关，新配置立刻生效（重启期间对话会断一下）。
"""
import json

import hermes_config as cfg
import launch_gateway


def get(handler):
    """返回当前模型、推理档位、可用模型、全部供应商与模型目录。"""
    # 刚切完模型 / 推理档位时网关在重启，前端会马上拉这个接口取新值：
    # 等网关回来再读，别让它拿到 502 或读到旧配置。
    if launch_gateway.is_restarting():
        launch_gateway.wait_ready(120)
    info = cfg.read_config_model()
    cur = info.get("provider") or ""
    info["available"] = cfg.list_models(cur)
    info["reasoning_levels"] = list(cfg.REASONING_LEVELS)
    catalog = cfg.catalog()
    info["providers"] = sorted(p for p, v in catalog.items() if v.get("models"))
    info["catalog"] = {p: sorted(catalog[p]["models"]) for p in info["providers"]}
    handler._json(info)


def _apply(handler, patch, label):
    """改 config.yaml（模型 / 推理档位），改完立刻重启网关。

    返回 (ok, err, backup)；没改动任何东西时 backup 为 None，也不重启。
    重启在后台线程里等冷启动，接口不跟着卡 20-60 秒——这期间 /api/* 会 502，
    页面自己会重试。
    """
    backup = patch()
    if backup is None:
        return True, None, None
    if not launch_gateway.restart(label=label):
        return False, "网关重启失败，新配置已写入但没生效", backup
    return True, None, backup


def switch(handler):
    """切模型：改 config.yaml + 写模型缓存，然后重启网关让新模型生效。"""
    try:
        n = int(handler.headers.get("Content-Length") or 0)
        body = json.loads(handler.rfile.read(n).decode("utf-8")) if n else {}
        new_model = (body.get("model") or "").strip()
        if not new_model:
            return handler._json({"error": "缺少 model 字段"}, 400)
        provider = (body.get("provider") or "").strip() or None
        base_url = (body.get("base_url") or "").strip() or None
        api_key = (body.get("api_key") or "").strip() or None

        def patch():
            backup = cfg.write_config_model(new_model, provider, base_url, api_key)
            if provider:
                cfg.cache_provider(provider, cfg.list_models(provider))
            return backup

        ok, err, backup = _apply(handler, patch, "switch model")
        if not ok:
            return handler._json({
                "ok": False,
                "model": new_model,
                "warning": "切换失败，" + err,
                "backup": backup,
            }, 200)
        return handler._json({"ok": True, "model": new_model,
                              "provider": provider, "backup": backup})
    except Exception as e:
        return handler._json({"error": str(e)}, 500)


def reasoning(handler):
    """POST /_reasoning：改 agent.reasoning_effort，然后重启网关让它生效。"""
    try:
        n = int(handler.headers.get("Content-Length") or 0)
        body = json.loads(handler.rfile.read(n).decode("utf-8")) if n else {}
        level = str(body.get("level") or "").strip().lower()
        if level not in cfg.REASONING_LEVELS:
            return handler._json({"error": "不支持的档位：" + level}, 400)

        ok, err, backup = _apply(handler, lambda: cfg.write_reasoning_effort(level),
                                 "switch reasoning")
        if not ok:
            return handler._json({"ok": False, "level": level,
                                  "warning": "切换失败，" + err, "backup": backup}, 200)
        return handler._json({"ok": True, "level": level, "backup": backup})
    except Exception as e:
        return handler._json({"error": str(e)}, 500)