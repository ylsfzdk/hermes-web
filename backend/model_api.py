"""GET / POST /_model：查询和切换当前模型。

只改 config.yaml，不碰网关进程——网关由用户手动重启才会读新配置。
"""
import json

import hermes_config as cfg


def get(handler):
    """返回当前模型、推理档位、可用模型、全部供应商与模型目录。"""
    info = cfg.read_config_model()
    cur = info.get("provider") or ""
    info["available"] = cfg.list_models(cur)
    info["reasoning_levels"] = list(cfg.REASONING_LEVELS)
    catalog = cfg.catalog()
    info["providers"] = sorted(p for p, v in catalog.items() if v.get("models"))
    info["catalog"] = {p: sorted(catalog[p]["models"]) for p in info["providers"]}
    handler._json(info)


def _apply(handler, patch):
    """改 config.yaml（模型 / 推理档位），不重启网关。

    返回 (ok, err, backup)；没改动任何东西时 backup 为 None。
    """
    backup = patch()
    if backup is None:
        return True, None, None
    return True, None, backup


def switch(handler):
    """只切模型：改 config.yaml + 写模型缓存。网关要手动重启才生效。"""
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

        ok, err, backup = _apply(handler, patch)
        if not ok:
            return handler._json({
                "ok": False,
                "model": new_model,
                "restored": True,
                "warning": "切换失败，" + err,
                "backup": backup,
            }, 200)
        return handler._json({"ok": True, "model": new_model,
                              "provider": provider, "backup": backup})
    except Exception as e:
        return handler._json({"error": str(e)}, 500)


def reasoning(handler):
    """POST /_reasoning：改 agent.reasoning_effort，网关要手动重启才生效。"""
    try:
        n = int(handler.headers.get("Content-Length") or 0)
        body = json.loads(handler.rfile.read(n).decode("utf-8")) if n else {}
        level = str(body.get("level") or "").strip().lower()
        if level not in cfg.REASONING_LEVELS:
            return handler._json({"error": "不支持的档位：" + level}, 400)

        ok, err, backup = _apply(handler, lambda: cfg.write_reasoning_effort(level))
        if not ok:
            return handler._json({"ok": False, "level": level,
                                  "warning": "切换失败，" + err, "backup": backup}, 200)
        return handler._json({"ok": True, "level": level, "backup": backup})
    except Exception as e:
        return handler._json({"error": str(e)}, 500)