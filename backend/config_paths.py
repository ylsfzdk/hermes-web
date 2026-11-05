"""路径与端口常量，所有模块共用。"""
import os

BACKEND = "http://127.0.0.1:8642"
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
PROXY_PREFIXES = ("/api/", "/v1/", "/health")

HERMES_DIR = os.path.expanduser("~/.hermes")
CONFIG = os.path.join(HERMES_DIR, "config.yaml")
MODELS_CACHE = os.path.join(HERMES_DIR, "provider_models_cache.json")
MODELS_DEV_CACHE = os.path.join(HERMES_DIR, "models_dev_cache.json")