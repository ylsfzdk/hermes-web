"""qqbot 读写的自检：在临时副本上跑 save → read → 断言，不碰真实的 .env / config.yaml。

    python backend\\_qqbot_selfcheck.py
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import hermes_config as cfg
from config_paths import CONFIG, ENV_FILE

tmpdir = os.path.join(HERE, ".qqbot-selfcheck")
shutil.rmtree(tmpdir, ignore_errors=True)
os.makedirs(tmpdir)

real_env, real_cfg = cfg.ENV_FILE, cfg.CONFIG
try:
    # 函数体在调用时才解析模块名，改这两个模块变量就够（别改 config_paths 那边）
    cfg.ENV_FILE = os.path.join(tmpdir, ".env")
    cfg.CONFIG = os.path.join(tmpdir, "config.yaml")
    with open(cfg.ENV_FILE, "w", encoding="utf-8") as f:
        f.write("DEEPSEEK_API_KEY=sk-x\n# keep me\n")
    with open(cfg.CONFIG, "w", encoding="utf-8") as f:
        f.write("model:\n  default: deepseek-flash\n")

    # 1) 保存：AppID/Secret + 启用 + pairing
    changed = cfg.save_qqbot({
        "app_id": "102010000000TEST", "client_secret": "sekrit",
        "enabled": True, "dm_authorization": "pairing",
        "allowed_users": "", "group_allowed_users": "", "home_channel": "OPEN-a",
        "markdown_support": True,
    })
    assert changed, "第一次保存应当有改动"
    info = cfg.read_qqbot()
    assert info["app_id"] == "102010000000TEST", info
    assert info["has_secret"] is True, info
    assert info["enabled"] is True, info
    assert info["dm_authorization"] == "pairing", info
    assert info["home_channel"] == "OPEN-a", info
    assert "sekrit" not in str(info), "密钥明文不该回传"

    text = open(cfg.CONFIG, encoding="utf-8").read()
    assert "platforms:\n  qqbot:\n    enabled: true\n" in text, text
    assert "markdown_support: true" in text, text
    env = open(cfg.ENV_FILE, encoding="utf-8").read()
    assert "DEEPSEEK_API_KEY=sk-x" in env and "# keep me" in env, env

    # 2) 原样再存：不该有任何改动（前端据此跳过网关重启）
    again = cfg.save_qqbot({
        "app_id": "102010000000TEST", "enabled": True,
        "dm_authorization": "pairing", "allowed_users": "",
        "group_allowed_users": "", "home_channel": "OPEN-a", "markdown_support": True,
    })
    assert again is False, "没改东西却报告有改动"

    # 3) open：QQ_ALLOW_ALL_USERS=true
    cfg.save_qqbot({"dm_authorization": "open"})
    assert cfg.read_qqbot()["dm_authorization"] == "open"
    assert cfg.read_env().get("QQ_ALLOW_ALL_USERS") == "true"

    # 4) allowlist + 白名单
    cfg.save_qqbot({"dm_authorization": "allowlist", "allowed_users": "OPEN-1,OPEN-2"})
    info = cfg.read_qqbot()
    assert info["dm_authorization"] == "allowlist", info
    assert info["allowed_users"] == "OPEN-1,OPEN-2", info
    assert cfg.read_env().get("QQ_ALLOW_ALL_USERS") == "false"

    # 5) 关掉
    cfg.save_qqbot({"enabled": False})
    assert cfg.read_qqbot()["enabled"] is False

    print("qqbot self-check OK")
finally:
    cfg.ENV_FILE, cfg.CONFIG = real_env, real_cfg
    shutil.rmtree(tmpdir, ignore_errors=True)