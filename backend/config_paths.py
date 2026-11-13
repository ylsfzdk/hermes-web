"""路径与端口常量，所有模块共用。"""
import os

BACKEND = "http://127.0.0.1:8642"
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
PROXY_PREFIXES = ("/api/", "/v1/", "/health")

# 源码启动的 Hermes：仓库 E:\hermes-agent-0.23.1，数据在家目录 .hermes-home。
# 父目录用相对路径算，仓库整体挪走只要改 HERMES_SRC 一行。
HERMES_SRC = os.environ.get("HERMES_SRC") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "hermes-agent-0.23.1")
HERMES_SRC = os.path.normpath(HERMES_SRC)
HERMES_PY = os.path.join(HERMES_SRC, ".venv", "Scripts", "python.exe")

HERMES_DIR = os.environ.get("HERMES_HOME") or os.path.join(HERMES_SRC, ".hermes-home")
CONFIG = os.path.join(HERMES_DIR, "config.yaml")
MODELS_CACHE = os.path.join(HERMES_DIR, "provider_models_cache.json")
MODELS_DEV_CACHE = os.path.join(HERMES_DIR, "models_dev_cache.json")