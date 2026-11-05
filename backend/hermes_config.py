"""读写 ~/.hermes 下的 config.yaml 与模型缓存。"""
import json
import os
import time

from config_paths import CONFIG, MODELS_CACHE, MODELS_DEV_CACHE


def read_config_model():
    """从 config.yaml 读当前模型与供应商。"""
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {"provider": None, "current": None}

    provider = None
    current = None
    base_url = None
    has_key = False
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
            elif s.startswith("base_url:") and base_url is None:
                base_url = s.split(":", 1)[1].strip() or None
            elif s.startswith("api_key:") and not has_key:
                has_key = (s.split(":", 1)[1].strip() or "null") not in ("null", "''", '""')
    return {"provider": provider, "current": current,
            "base_url": base_url, "has_key": has_key}


def catalog():
    """models.dev 全量目录 {provider: {model_id: 规格}}，只读。"""
    try:
        with open(MODELS_DEV_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def list_models(provider):
    """读 provider 的候选模型（本地缓存优先，缺的从 models.dev 全量目录补齐）。"""
    models = []
    try:
        with open(MODELS_CACHE, "r", encoding="utf-8") as f:
            models = list(json.load(f).get(provider, {}).get("models", []))
    except Exception:
        pass
    models += [m for m in catalog().get(provider, {}).get("models", {}) if m not in models]
    return models





def cache_provider(provider, models):
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


def write_config_model(new_model, provider=None, base_url=None, api_key=None):
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

    # 先存改动前的原文，再写新内容；否则 .bak 和 config.yaml 一样新，没法回滚
    backup = CONFIG + ".bak"
    with open(CONFIG, "r", encoding="utf-8", newline="") as f:
        old = f.read()
    try:
        with open(backup, "w", encoding="utf-8", newline="") as f:
            f.write(old)
    except Exception:
        backup = None

    try:
        with open(CONFIG, "w", encoding="utf-8", newline="") as f:
            f.writelines(lines)
    except PermissionError:
        raise RuntimeError("没有权限修改 config.yaml，请用普通用户身份运行 start.bat")
    return backup


def restore_config(backup):
    """把 config.yaml 还原成 .bak 里的内容（改动前）。返回是否成功。"""
    if not backup or not os.path.exists(backup):
        return False
    try:
        with open(backup, "r", encoding="utf-8", newline="") as f:
            old = f.read()
        with open(CONFIG, "w", encoding="utf-8", newline="") as f:
            f.write(old)
        return True
    except Exception:
        return False