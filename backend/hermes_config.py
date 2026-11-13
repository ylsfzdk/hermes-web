"""读写 ~/.hermes 下的 config.yaml 与模型缓存。"""
import json
import os
import time

from config_paths import CONFIG, MODELS_CACHE, MODELS_DEV_CACHE


# Hermes 认可档位（hermes_constants.VALID_REASONING_EFFORTS），空串 = 服务端默认
REASONING_LEVELS = ("", "none", "minimal", "low", "medium", "high", "xhigh")


def _yaml_str(v):
    """YAML 标量：能裸写就裸写，否则加引号。"""
    v = str(v)
    if v and all(c.isalnum() or c in "-_." for c in v):
        return v
    return json.dumps(v)


def _top_level(text, name):
    """顶层段 name: 的段头下标；注释行和缩进行都不算。"""
    for i, line in enumerate(text.splitlines()):
        s = line.split("#", 1)[0].rstrip()
        if s.startswith(name + ":") and s == s.lstrip():
            return i
    return None


def _section(text, name):
    """返回顶层段 name: 下的所有行（不含段头）；段不存在返回 []。"""
    lines = text.splitlines()
    start = _top_level(text, name)
    if start is None:
        return []
    out = []
    for nxt in lines[start + 1:]:
        if nxt.strip() and not nxt[0].isspace():
            break
        out.append(nxt)
    return out


def _section_get(text, section, key):
    for line in _section(text, section):
        s = line.strip()
        if s.startswith("#"):
            continue
        s = s.split("#", 1)[0].rstrip() if "#" in s else s
        if s.startswith(key + ":"):
            return s.split(":", 1)[1].strip()
    return None


def _section_set(lines, section, key, value):
    """过程化改 YAML：段内改/加一行，段不存在就新建。"""
    start = next((i for i, l in enumerate(lines)
                  if not l.startswith((" ", "\t", "#")) and l.startswith(section + ":")), None)
    if start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines += [section + ":\n", "  " + key + ": " + value + "\n"]
        return lines
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].strip() and not lines[i][0].isspace():
            end = i
            break

    indent = "  "
    for i in range(start + 1, end):
        s = lines[i]
        if s.strip():
            indent = s[:len(s) - len(s.lstrip())]
            if s.strip().startswith(key + ":"):
                lines[i] = indent + key + ": " + value + "\n"
                return lines
    lines.insert(end, indent + key + ": " + value + "\n")
    return lines


def _read_text():
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _write_text(text):
    backup = CONFIG + ".bak"
    try:
        with open(backup, "w", encoding="utf-8", newline="") as f:
            f.write(_read_text())
    except Exception:
        backup = None
    try:
        with open(CONFIG, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    except PermissionError:
        raise RuntimeError("没有权限修改 config.yaml，请用普通用户身份运行 start.bat；"
                           "或先给 %s 加写权限（同名 .bak 也要能写）" % CONFIG)
    return backup


def read_config_model():
    """从 config.yaml 读当前模型、供应商与推理档位。

    model: 段和 agent: 段谁在前都可能（新版 config.yaml 里 agent 在 model 前面），
    所以按段找，不按文件顺序扫。
    """
    return read_config_model_text(_read_text())


def read_config_model_text(text):
    """按 config.yaml 文本解析（自检直接喂字符串，不碰磁盘）。"""
    provider = current = base_url = None
    has_key = False
    for s in (_section(text, "model")):
        s = s.strip()
        if s.startswith("#"):
            continue
        s = s.split("#", 1)[0].rstrip() if "#" in s else s
        if s.startswith("provider:") and provider is None:
            provider = s.split(":", 1)[1].strip() or None
        elif s.startswith("default:") and current is None:
            current = s.split(":", 1)[1].strip() or None
        elif s.startswith("base_url:") and base_url is None:
            base_url = s.split(":", 1)[1].strip() or None
        elif s.startswith("api_key:") and not has_key:
            has_key = (s.split(":", 1)[1].strip() or "null") not in ("null", "''", '""')
    if current is None:
        # 只有 name: 没有 default: 时 hermes 实际取 name:
        current = (_section_get(text, "model", "name") or "").strip() or None
    return {"provider": provider, "current": current,
            "base_url": base_url, "has_key": has_key,
            "reasoning": (_section_get(text, "agent", "reasoning_effort") or "")
                         .strip("'\"")}


def write_reasoning_effort(level):
    """写 agent.reasoning_effort（网关唯一的推理档位来源）。返回备份路径；
    值没变时返回 None，调用方据此跳过网关重启。"""
    text = _read_text()
    if (_section_get(text, "agent", "reasoning_effort") or "").strip('"\'') == level:
        return None
    lines = _section_set(text.splitlines(True), "agent",
                         "reasoning_effort", _yaml_str(level))
    return _write_text("".join(lines))


if __name__ == "__main__":
    # 自检：改一行不碰别的，段缺失能新建，同值不写文件
    t = "model:\n  default: a\nagent:\n  max_turns: 150\n  reasoning_effort: ''\n"
    out = "".join(_section_set(t.splitlines(True), "agent", "reasoning_effort", "high"))
    assert "  reasoning_effort: high\n" in out and "max_turns: 150" in out, out
    assert "default: a" in out, out
    out2 = "".join(_section_set(["model:\n"], "agent", "reasoning_effort", "\"x\""))
    assert out2 == 'model:\nagent:\n  reasoning_effort: "x"\n', repr(out2)
    assert _section_get("agent:\n  reasoning_effort: high\n", "agent", "reasoning_effort") == "high"
    assert _yaml_str("") == '""' and _yaml_str("high") == "high"

    # 新版 config.yaml 的真实形状：大段注释在前，agent: 在 model: 之前，段内还有注释
    real = (
        "agent:\n  max_turns: 150\n  reasoning_effort: medium\n"
        "_config_version: 53\n"
        "# ── Fallback Model ──\n# fallback_model:\n#   provider: openrouter\n"
        "model:\n  default: deepseek-flash\n  provider: deepseek\n"
        "  base_url: https://api.deepseek.com  # 官方端点\n"
        "gateway:\n  service_install_choice: decline\n"
    )
    info = read_config_model_text(real)
    assert info["provider"] == "deepseek", info
    assert info["current"] == "deepseek-flash", info
    assert info["base_url"] == "https://api.deepseek.com", info
    assert info["reasoning"] == "medium", info

    # 改模型：只动 model 段里的两行，行尾注释留着，别的段一个字不变
    lines = real.splitlines(True)
    start = next(i for i, l in enumerate(lines) if l.startswith("model:"))
    end = next(i for i in range(start + 1, len(lines)) if not lines[i][0].isspace())
    for i in range(start + 1, end):
        s = lines[i].lstrip()
        ind = lines[i][:len(lines[i]) - len(s)]
        if s.startswith("default:"):
            lines[i] = ind + "default: deepseek-v4-pro\n"
        elif s.startswith("base_url:"):
            lines[i] = ind + "base_url: https://x/v1  # 官方端点\n"
    out = "".join(lines)
    assert "default: deepseek-v4-pro" in out and "# 官方端点" in out, out
    assert out.startswith(real.split("model:")[0]), out
    print("ok")


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

    # model 段头：跳过注释行和缩进行（新版 config.yaml 里 model: 前面有一大段注释）
    start = next((i for i, l in enumerate(lines)
                  if not l.startswith((" ", "\t", "#")) and l.startswith("model:")), None)
    if start is None:
        raise RuntimeError("config.yaml 里没找到顶层 model: 段")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].strip() and not lines[i][0].isspace():
            end = i
            break

    changed = False
    seen_provider = False
    seen_key = False
    provider_at = None  # model 段结束前最后一个 provider 行的下标
    key_at = None

    for i in range(start + 1, end):
        line = lines[i]
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
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
        if stripped.startswith("base_url:"):
            if base_url:
                # 只换值，保留行尾注释
                comment = line.split("#", 1)[1] if "#" in line else ""
                lines[i] = indent + "base_url: " + base_url
                lines[i] += ("  #" + comment.rstrip() + "\n") if comment else "\n"
            continue
        if stripped.startswith("default:") and not changed:
            lines[i] = indent + "default: " + new_model + "\n"
            changed = True
            continue
        # hermes 实际取的是 name: 而不只是 default:，两个都改，否则切换不生效
        if stripped.startswith("name:"):
            lines[i] = indent + "name: " + new_model + "\n"

    if not changed:
        raise RuntimeError("config.yaml 的 model 段里没找到 default 字段")

    if provider and not seen_provider:
        if provider_at is None:
            raise RuntimeError("config.yaml 的 model 段里没找到 provider 字段")
        lines.insert(provider_at + 1, "  provider: " + provider + "\n")

    if api_key and not seen_key:
        if key_at is None:
            raise RuntimeError("config.yaml 的 model 段里没找到 api_key 字段")
        lines.insert(key_at + 1, "  api_key: " + json.dumps(api_key) + "\n")

    with open(CONFIG, "r", encoding="utf-8", newline="") as f:
        old = f.read()
    backup = _backup(old)
    _write_lines(backup, lines)
    return backup


def _backup(old):
    """先存改动前的原文，再写新内容；否则 .bak 和 config.yaml 一样新，没法回滚。"""
    backup = CONFIG + ".bak"
    try:
        with open(backup, "w", encoding="utf-8", newline="") as f:
            f.write(old)
    except Exception:
        return None
    return backup


def _write_lines(backup, lines):
    try:
        with open(CONFIG, "w", encoding="utf-8", newline="") as f:
            f.writelines(lines)
    except PermissionError:
        raise RuntimeError("没有权限修改 config.yaml，请用普通用户身份运行 start.bat；"
                           "或先给 %s 加写权限（同名 .bak 也要能写）" % CONFIG)
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