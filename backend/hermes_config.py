"""读写 ~/.hermes 下的 config.yaml、.env 与模型缓存。"""
import json
import os
import time

from config_paths import CONFIG, ENV_FILE, MODELS_CACHE, MODELS_DEV_CACHE


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


# ---------------- 消息平台（目前只有 qqbot）：.env 凭据 + config.yaml 开关 ----------------
# 密钥只回传"有没有配"，明文不出本进程，也不进 .bak 之外的任何文件

QQ_AUTHZ = {
    "pairing": "扫码人自动进白名单，其他人先发配对码等你审批",
    "allowlist": "只有白名单里的 OpenID 能用",
    "open": "任何私聊都能用（慎用）",
}

QQ_ENV_KEYS = ("QQ_APP_ID", "QQ_CLIENT_SECRET", "QQ_ALLOWED_USERS",
               "QQ_GROUP_ALLOWED_USERS", "QQ_ALLOW_ALL_USERS", "QQBOT_HOME_CHANNEL")


def _env_split(line):
    """.env 一行 → (key, value)；不是赋值行就先返回 (None, None)。
    值支持引号；不带引号时行尾 " #xxx" 算注释（和 dotenv 一致）。"""
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None, None
    if s.startswith("export "):
        s = s[7:].lstrip()
    k, v = s.split("=", 1)
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    elif " #" in v:
        v = v.split(" #", 1)[0].rstrip()
    return k.strip(), v


def read_env():
    """<HERMES_HOME>/.env → dict；注释、空行、export 前缀都按 dotenv 的规矩忽略。"""
    out = {}
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return out
    for line in text.splitlines():
        k, v = _env_split(line)
        if k is not None:
            out[k] = v
    return out


def write_env(updates):
    """逐行改 .env：已有的键原位换值（行尾注释保留），没有的追加到末尾。
    先存 .env.bak 再写；一个字节没变就不落盘。返回备份路径或 None。"""
    try:
        with open(ENV_FILE, "r", encoding="utf-8", newline="") as f:
            old = f.read()
    except FileNotFoundError:
        old = ""
    lines = old.splitlines(True)
    pending = dict(updates)
    for i, line in enumerate(lines):
        key, cur = _env_split(line)
        if key not in pending:
            continue
        val = pending.pop(key)
        if cur == val:
            continue                      # 值没变就原样留着，连注释格式都不动
        comment = line.split("#", 1)[1].rstrip("\r\n") if "#" in line else ""
        lines[i] = key + "=" + val + ("  #" + comment + "\n" if comment else "\n")
    if pending:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines += ["%s=%s\n" % (k, v) for k, v in pending.items()]
    new = "".join(lines)
    if new == old:
        return None
    backup = None
    try:
        with open(ENV_FILE + ".bak", "w", encoding="utf-8", newline="") as f:
            f.write(old)
        backup = ENV_FILE + ".bak"
    except Exception:
        pass
    try:
        with open(ENV_FILE, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    except PermissionError:
        raise RuntimeError("没有权限修改 .env：%s" % ENV_FILE)
    return backup


def _nested_get(text, section, sub, key):
    """读 platforms.<section>.<sub>.<key>（只认两段缩进，够用了）。"""
    in_sub = False
    for line in _section(text, section):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = s.split("#", 1)[0].rstrip()
        indent = len(line) - len(line.lstrip())
        if indent == 2:
            in_sub = s.startswith(sub + ":")
        elif in_sub and indent == 4 and s.startswith(key + ":"):
            return s.split(":", 1)[1].strip()
    return None


def _nested_set(lines, section, sub, key, value):
    """设 platforms.<section>.<sub>.<key>。段和子段都按"跟已有兄弟行对齐"处理；
    缺什么补什么，已有的一行原位改掉。"""
    # 找 section 段（顶层 platforms: 下的两格缩进段）
    plat = _top_level("".join(lines), "platforms")
    if plat is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines += ["platforms:\n", "  " + sub + ":\n", "    " + key + ": " + value + "\n"]
        return lines

    def block_end(idx):
        """idx 行所属块的第一段结束位置：缩进 <= idx 行缩进且非空的下一行。"""
        base = len(lines[idx]) - len(lines[idx].lstrip())
        for j in range(idx + 1, len(lines)):
            if lines[j].strip() and (len(lines[j]) - len(lines[j].lstrip())) <= base:
                return j
        return len(lines)

    sub_at = None
    for i in range(plat + 1, block_end(plat)):
        l = lines[i]
        if l.strip() and (len(l) - len(l.lstrip())) == 2 and l.lstrip().startswith(sub + ":"):
            sub_at = i
            break
    if sub_at is None:
        lines.insert(block_end(plat), "  " + sub + ":\n")
        sub_at = block_end(plat) - 1
        lines.insert(block_end(sub_at), "    " + key + ": " + value + "\n")
        return lines
    for i in range(sub_at + 1, block_end(sub_at)):
        l = lines[i]
        if l.strip() and (len(l) - len(l.lstrip())) == 4 and l.lstrip().startswith(key + ":"):
            ind = l[:len(l) - len(l.lstrip())]
            lines[i] = ind + key + ": " + value + "\n"
            return lines
    lines.insert(block_end(sub_at), "    " + key + ": " + value + "\n")
    return lines


def read_qqbot():
    """QQ Bot 的当前配置：只回安全的字段，密钥只回"有没有配"。"""
    text = _read_text()
    env = read_env()
    enabled_raw = _nested_get(text, "platforms", "qqbot", "enabled")
    allowed = env.get("QQ_ALLOWED_USERS", "")
    if env.get("QQ_ALLOW_ALL_USERS", "").strip().lower() in ("1", "true", "yes"):
        authz = "open"
    elif allowed.strip():
        authz = "allowlist"
    else:
        authz = "pairing"
    return {
        "enabled": (enabled_raw or "false").strip().lower() in ("true", "yes", "1"),
        "app_id": env.get("QQ_APP_ID", ""),
        "has_secret": bool(env.get("QQ_CLIENT_SECRET", "")),
        "dm_authorization": authz,
        "allowed_users": env.get("QQ_ALLOWED_USERS", ""),
        "group_allowed_users": env.get("QQ_GROUP_ALLOWED_USERS", ""),
        "home_channel": env.get("QQBOT_HOME_CHANNEL", ""),
        "markdown_support": (_nested_get(text, "platforms", "qqbot", "markdown_support")
                             or "true").strip().lower() in ("true", "yes", "1"),
        "authz_modes": QQ_AUTHZ,
    }


def save_qqbot(settings):
    """把 settings 写进 .env + config.yaml。settings 里 None 表示"这次不动它"
    （比如没重填的密钥）。有任何改动返回 True，全都没变返回 False，
    调用方据此决定要不要重启网关。"""
    cur = read_qqbot()
    env = read_env()
    updates = {}

    app_id = settings.get("app_id")
    if app_id is not None and app_id.strip() != cur["app_id"]:
        updates["QQ_APP_ID"] = app_id.strip()
    secret = (settings.get("client_secret") or "").strip()
    if secret:
        updates["QQ_CLIENT_SECRET"] = secret
    mode = settings.get("dm_authorization")
    if mode is not None:
        if mode not in QQ_AUTHZ:
            raise RuntimeError("私聊授权方式只能是 pairing / allowlist / open")
        updates["QQ_ALLOW_ALL_USERS"] = "true" if mode == "open" else "false"
        # pairing 下白名单可以留空（全靠配对审批），填了就是额外放行
        updates["QQ_ALLOWED_USERS"] = (settings.get("allowed_users") or "").strip()
    elif settings.get("enabled") is not None:
        updates["QQ_ALLOW_ALL_USERS"] = "false" if not settings["enabled"] else env.get(
            "QQ_ALLOW_ALL_USERS", "false")
    if settings.get("group_allowed_users") is not None:
        updates["QQ_GROUP_ALLOWED_USERS"] = settings["group_allowed_users"].strip()
    if settings.get("home_channel") is not None:
        updates["QQBOT_HOME_CHANNEL"] = settings["home_channel"].strip()

    env_updates = {k: v for k, v in updates.items() if env.get(k, "") != v}
    changes = bool(env_updates)
    if env_updates:
        write_env(env_updates)

    # config.yaml 的 platforms.qqbot.enabled / markdown_support
    lines = _read_text().splitlines(True)
    for key, field in (("enabled", "enabled"), ("markdown_support", "markdown_support")):
        if settings.get(field) is None:
            continue
        want = "true" if settings[field] else "false"
        if (_nested_get("".join(lines), "platforms", "qqbot", key) or "").lower() != want:
            lines = _nested_set(lines, "platforms", "qqbot", key, want)
            changes = True
    new = "".join(lines)
    if new != _read_text():
        _write_text(new)
    return changes


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

    # ---- qqbot：.env 读写 + platforms.qqbot 两段缩进 ----
    text = ("model:\n  default: x\nplatforms:\n  telegram:\n    enabled: true\n"
            "  qqbot:\n    enabled: false   # 先关着\n")
    assert _nested_get(text, "platforms", "qqbot", "enabled") == "false"
    assert _nested_get(text, "platforms", "telegram", "enabled") == "true"
    assert _nested_get(text, "platforms", "qqbot", "missing") is None

    lines = _nested_set(text.splitlines(True), "platforms", "qqbot", "enabled", "true")
    got = "".join(lines)
    assert "    enabled: true\n" in got and "  telegram:\n    enabled: true" in got, got
    # 子段不存在就补，父段不存在也补
    lines = _nested_set(text.splitlines(True), "platforms", "qqbot", "markdown_support", "true")
    assert "    markdown_support: true\n" in "".join(lines)
    lines = _nested_set(["model:\n  default: x\n"], "platforms", "qqbot", "enabled", "true")
    assert "".join(lines) == "model:\n  default: x\nplatforms:\n  qqbot:\n    enabled: true\n"

    # .env 解析 + 写入：临时目录跑一遍完整闭环，不碰真实的 .env
    import shutil
    global ENV_FILE
    tmpdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env-selfcheck")
    os.makedirs(tmpdir, exist_ok=True)
    real_env = ENV_FILE
    try:
        ENV_FILE = os.path.join(tmpdir, ".env")
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("# comment\nA=1\nB='two words'\nexport C=3  # tail\n")
        env = read_env()
        assert env == {"A": "1", "B": "two words", "C": "3"}, env
        assert write_env({"A": "1"}) is None              # 没变就不落盘
        write_env({"B": "new", "D": "4"})
        assert read_env() == {"A": "1", "B": "new", "C": "3", "D": "4"}, read_env()
        assert "  # tail" in open(ENV_FILE, encoding="utf-8").read()
        assert os.path.exists(ENV_FILE + ".bak")
    finally:
        ENV_FILE = real_env
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("ok")
