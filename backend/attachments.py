"""会话级附件：基础校验（格式 + 大小）。

POST   /_attachments   multipart/form-data: file + session_id  -> 存盘 + 元数据
GET    /_attachments?session_id=xxx                  -> 该会话的附件列表
DELETE /_attachments/<id>                            -> 删一个附件

存放：$HERMES_HOME/sessions/<会话ID>/attachments/<随机名>.<ext>
索引：$HERMES_HOME/sessions/<会话ID>/attachments/index.json
和会话 ID 强绑定，删会话时整个目录跟着删。

本文件只管"校验 + 落盘"。--self-check 可单独跑：python attachments.py
"""
import json
import os
import re
import secrets
import shutil
import sys
import time
import urllib.parse
from email import policy
from email.parser import BytesParser

from config_paths import HERMES_DIR

MAX_BYTES = 20 * 1024 * 1024      # 单文件上限
MAGIC_BYTES = 16                  # 只读开头这段做真实格式探测

# 支持的格式：扩展名 -> 显示名。不在这里的一律拒收。
TYPES = {
    # 文档
    "pdf": "PDF", "doc": "Word", "docx": "Word", "odt": "OpenDocument 文本",
    "rtf": "RTF", "txt": "纯文本", "md": "Markdown", "markdown": "Markdown",
    "csv": "CSV", "tsv": "TSV", "epub": "EPUB", "mobi": "Mobi",
    # 表格
    "xls": "Excel", "xlsx": "Excel", "xlsm": "Excel（宏）", "ods": "OpenDocument 表格",
    "numbers": "Numbers",
    # 演示文稿
    "ppt": "PowerPoint", "pptx": "PowerPoint", "ppsx": "PowerPoint 放映",
    "odp": "OpenDocument 演示", "key": "Keynote",
    # 图片
    "png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "gif": "GIF", "webp": "WebP",
    "bmp": "BMP", "tif": "TIFF", "tiff": "TIFF", "svg": "SVG", "ico": "图标",
    "avif": "AVIF", "heic": "HEIC",
    # 代码 / 配置 / 数据
    "py": "Python", "js": "JavaScript", "mjs": "JavaScript", "cjs": "JavaScript",
    "ts": "TypeScript", "tsx": "TypeScript", "jsx": "JavaScript",
    "java": "Java", "kt": "Kotlin", "c": "C", "h": "C 头文件", "cpp": "C++",
    "hpp": "C++ 头文件", "cs": "C#", "go": "Go", "rs": "Rust", "rb": "Ruby",
    "php": "PHP", "swift": "Swift", "scala": "Scala", "r": "R", "lua": "Lua",
    "dart": "Dart", "m": "Objective-C / MATLAB", "sh": "Shell", "bat": "批处理",
    "ps1": "PowerShell", "sql": "SQL", "html": "HTML", "htm": "HTML",
    "css": "CSS", "scss": "SCSS", "less": "Less", "vue": "Vue", "svelte": "Svelte",
    "xml": "XML", "yaml": "YAML", "yml": "YAML", "toml": "TOML", "ini": "INI",
    "cfg": "配置", "conf": "配置", "env": "环境变量", "json": "JSON",
    "jsonl": "JSON Lines", "log": "日志", "tex": "LaTeX", "rst": "reStructuredText",
    "properties": "Properties", "gradle": "Gradle",
}

# 这些扩展名必须和文件头对得上，防止"改个后缀就混进来"
MAGIC = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"], "jpeg": [b"\xff\xd8\xff"],
    "gif": [b"GIF87a", b"GIF89a"],
    "webp": [b"RIFF"],          # RIFF....WEBP，再单独看偏移 8
    "bmp": [b"BM"],
    "tif": [b"II*\x00", b"MM\x00*"], "tiff": [b"II*\x00", b"MM\x00*"],
    "ico": [b"\x00\x00\x01\x00"],
    "heic": [b"ftypheic", b"ftypheix", b"ftypmif1"],
    "avif": [b"ftypavif"],
    "epub": [b"PK\x03\x04"],
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "ppt": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "docx": [b"PK\x03\x04"], "xlsx": [b"PK\x03\x04"], "pptx": [b"PK\x03\x04"],
    "xlsm": [b"PK\x03\x04"], "ppsx": [b"PK\x03\x04"],
    "odt": [b"PK\x03\x04"], "ods": [b"PK\x03\x04"], "odp": [b"PK\x03\x04"],
}
# 这些机器上不一定有 zf 前缀以外的 OOXML 特征，PK 已足够

_SID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def sessions_dir():
    return os.path.join(HERMES_DIR, "sessions")


def clean_session_id(sid):
    """会话 ID 要拼进路径，先挡住 .. 和分隔符。"""
    sid = str(sid or "").strip()
    if not _SID.match(sid) or ".." in sid:
        return None
    return sid


def attach_dir(sid):
    return os.path.join(sessions_dir(), sid, "attachments")


def index_path(sid):
    return os.path.join(attach_dir(sid), "index.json")


def load_index(sid):
    try:
        with open(index_path(sid), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_index(sid, items):
    d = attach_dir(sid)
    os.makedirs(d, exist_ok=True)
    tmp = index_path(sid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, index_path(sid))


def display_name(filename):
    """只留文件名本体：去目录、去控制字符、去前导点。"""
    name = re.split(r"[\\/]", str(filename or ""))[-1]
    name = "".join(ch for ch in name if ch >= " " and ch != "\x7f").strip()
    return name.lstrip(".") or "file"


def check_file(filename, size, head):
    """基础校验。返回 (info, error)，error 为 None 表示通过。

    head 是文件开头 MAGIC_BYTES 字节，用来验真实格式。
    """
    name = display_name(filename)
    base, dot, ext = name.rpartition(".")
    ext = ext.lower() if dot else ""
    if not ext:
        return None, "不支持的文件格式：%s（没有扩展名）" % name
    if ext not in TYPES:
        return None, "不支持的文件格式：.%s" % ext
    if size <= 0:
        return None, "文件是空的"
    if size > MAX_BYTES:
        return None, "文件太大：%.1f MB，上限 %d MB" % (size / 1048576, MAX_BYTES // 1048576)

    magic = MAGIC.get(ext)
    if magic:
        ok = any(head.startswith(m) for m in magic)
        if ok and ext == "webp":
            ok = head[8:12] == b"WEBP"
        if not ok:
            return None, "文件内容与扩展名 .%s 不符，已拒绝" % ext
    return {"name": name, "ext": ext, "type": TYPES[ext], "size": size}, None


def store(sid, filename, data):
    """校验 + 存盘。返回 (item, error)。"""
    info, err = check_file(filename, len(data), data[:MAGIC_BYTES])
    if err:
        return None, err

    d = attach_dir(sid)
    os.makedirs(d, exist_ok=True)
    stored = "%s.%s" % (secrets.token_hex(8), info["ext"])
    with open(os.path.join(d, stored), "wb") as f:
        f.write(data)

    item = dict(info, id=secrets.token_hex(6), stored=stored, ts=int(time.time()),
                sent=False)
    items = load_index(sid)
    items.append(item)
    save_index(sid, items)
    return item, None


def mark_sent(sid, ids):
    """消息发出去了：这些附件转成历史附件（sent=True），不再回到输入框标签。"""
    items = load_index(sid)
    hit = False
    for x in items:
        if x.get("id") in ids and not x.get("sent"):
            x["sent"] = True
            hit = True
    if hit:
        save_index(sid, items)
    return hit


def remove(sid, aid):
    """删一个附件。返回是否删到。"""
    items = load_index(sid)
    keep = [x for x in items if x.get("id") != aid]
    if len(keep) == len(items):
        return False
    for x in items:
        if x.get("id") == aid and x.get("stored"):
            try:
                os.remove(os.path.join(attach_dir(sid), x["stored"]))
            except OSError:
                pass
    save_index(sid, keep)
    return True


# ============ HTTP 入口 ============

def _read_body(handler, limit):
    """读完整请求体，超限就报错。返回 (bytes, error)。"""
    try:
        n = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        return b"", "Content-Length 不合法"
    if n > limit:
        return b"", "上传内容太大"
    return handler.rfile.read(n) if n else b"", None


def upload(handler):
    sid = clean_session_id(urllib.parse.parse_qs(
        urllib.parse.urlsplit(handler.path).query).get("session_id", [""])[0])
    if not sid:
        return handler._json({"error": "缺少或非法的 session_id"}, 400)

    # 留一点余量给 multipart 的头部和边界
    body, err = _read_body(handler, MAX_BYTES + 64 * 1024)
    if err:
        return handler._json({"error": err}, 413)

    ctype = handler.headers.get("Content-Type") or ""
    if "multipart/form-data" not in ctype:
        return handler._json({"error": "需要 multipart/form-data"}, 400)

    try:
        msg = BytesParser(policy=policy.HTTP).parsebytes(
            b"Content-Type: " + ctype.encode("latin-1") + b"\r\n\r\n" + body)
        part = next((p for p in msg.iter_parts()
                     if p.get_param("name", header="content-disposition") == "file"), None)
        data = part.get_payload(decode=True) if part else None
    except Exception as e:
        return handler._json({"error": "解析上传内容失败：" + str(e)}, 400)
    if not part or data is None:
        return handler._json({"error": "没有收到 file 字段"}, 400)

    name = part.get_filename() or ""
    if "commit=0" in urllib.parse.urlsplit(handler.path).query:
        # 预检：只校验，不落盘，供前端点发送前先拦一道
        info, err = check_file(name, len(data), data[:MAGIC_BYTES])
        if err:
            return handler._json({"error": err}, 400)
        return handler._json({"ok": True, "file": info})

    try:
        item, err = store(sid, name, data)
    except OSError as e:
        return handler._json({"error": "保存失败：" + str(e)}, 500)
    if err:
        return handler._json({"error": err}, 400)
    return handler._json({"ok": True, "file": item})


def listing(handler):
    sid = clean_session_id(urllib.parse.parse_qs(
        urllib.parse.urlsplit(handler.path).query).get("session_id", [""])[0])
    if not sid:
        return handler._json({"error": "缺少或非法的 session_id"}, 400)
    return handler._json({"ok": True, "files": load_index(sid)})


def sent(handler):
    """POST /_attachments/sent?session_id=xxx  body: {"ids": [...]}"""
    sid = clean_session_id(urllib.parse.parse_qs(
        urllib.parse.urlsplit(handler.path).query).get("session_id", [""])[0])
    if not sid:
        return handler._json({"error": "缺少或非法的 session_id"}, 400)
    body, err = _read_body(handler, 64 * 1024)
    if err:
        return handler._json({"error": err}, 413)
    try:
        ids = set(json.loads(body.decode("utf-8")).get("ids") or [])
    except (ValueError, AttributeError):
        return handler._json({"error": "请求体要是 {\"ids\": [...]}"}, 400)
    if not ids:
        return handler._json({"error": "没有附件 id"}, 400)
    try:
        mark_sent(sid, ids)
    except OSError as e:
        return handler._json({"error": "保存失败：" + str(e)}, 500)
    return handler._json({"ok": True})


def delete(handler):
    """DELETE /_attachments/<id>?session_id=xxx"""
    path = urllib.parse.urlsplit(handler.path).path
    aid = urllib.parse.unquote(path[len("/_attachments/"):]).strip("/")
    sid = clean_session_id(urllib.parse.parse_qs(
        urllib.parse.urlsplit(handler.path).query).get("session_id", [""])[0])
    if not sid or not aid:
        return handler._json({"error": "缺少 session_id 或附件 id"}, 400)
    try:
        found = remove(sid, aid)
    except OSError as e:
        return handler._json({"error": "删除失败：" + str(e)}, 500)
    if not found:
        return handler._json({"error": "附件不存在"}, 404)
    return handler._json({"ok": True})


def purge(handler):
    """DELETE /_attachments?session_id=xxx：删整个 sessions/<会话ID>/ 目录（删会话时调）。

    网关删会话只删 state.db 记录，不碰 sessions/<id>/ 目录，所以这里自己清。
    范围是整个会话目录（附件只是其中一个子目录），但不动 sessions/ 根下的
    request_dump_*.json，也不动 sessions/saved/（那是主动导出的存档）。
    """
    sid = clean_session_id(urllib.parse.parse_qs(
        urllib.parse.urlsplit(handler.path).query).get("session_id", [""])[0])
    if not sid:
        return handler._json({"error": "缺少或非法的 session_id"}, 400)

    root = os.path.realpath(sessions_dir())
    target = os.path.realpath(os.path.join(root, sid))
    # 只允许删 sessions/ 下正好一层、名字等于会话 ID 的目录
    if os.path.dirname(target) != root or os.path.basename(target) != sid:
        return handler._json({"error": "路径异常，已拒绝"}, 400)
    try:
        existed = os.path.isdir(target)
        if existed:
            shutil.rmtree(target)
    except OSError as e:
        return handler._json({"error": "删除失败：" + str(e)}, 500)
    return handler._json({"ok": True, "removed": existed})


# ============ 自检 ============
def _self_check():
    global HERMES_DIR
    backing = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".attach-selfcheck")
    HERMES_DIR = os.path.join(backing, ".hermes")
    sid = "api_1793876822_e94fb2fe"

    assert check_file("a.PDF", 10, b"%PDF-1.7")[1] is None, "大写扩展名应通过"
    assert check_file("a.pdf", 10, b"PK\x03\x04")[1], "假 PDF 应被拦住"
    assert check_file("a.exe", 10, b"MZ")[1], "不支持格式应被拒"
    assert check_file("noext", 10, b"x")[1], "无扩展名应被拒"
    assert check_file("big.txt", MAX_BYTES + 1, b"x")[1], "超限应被拒"
    assert check_file("empty.txt", 0, b"")[1], "空文件应被拒"
    assert check_file("ws.png", 10, b"\x89PNG\r\n\x1a\nxxxx")[1] is None
    assert check_file("w.webp", 10, b"RIFF\x00\x00\x00\x00WEBP")[1] is None
    assert check_file("w.webp", 10, b"RIFF\x00\x00\x00\x00XXXX")[1], "假 webp 应被拦"
    assert clean_session_id("../etc") is None
    assert clean_session_id(sid) == sid
    assert display_name("C:\\Users\\x\\报告.docx") == "报告.docx"

    f1, err = store(sid, "报告.docx", b"PK\x03\x04rest")
    assert err is None and f1["type"] == "Word", err
    assert os.path.isfile(os.path.join(attach_dir(sid), f1["stored"])), "文件没落盘"
    assert len(load_index(sid)) == 1
    assert attach_dir(sid).startswith(os.path.join(HERMES_DIR, "sessions", sid)), "目录要绑会话"
    assert remove(sid, f1["id"]) and load_index(sid) == []
    assert not os.path.exists(os.path.join(attach_dir(sid), f1["stored"])), "文件没删掉"
    assert len(TYPES) >= 70, "格式表数量不对：%d" % len(TYPES)
    import shutil
    shutil.rmtree(backing, ignore_errors=True)
    print("attachments self-check OK (%d 种格式)" % len(TYPES))


if __name__ == "__main__":
    _self_check()