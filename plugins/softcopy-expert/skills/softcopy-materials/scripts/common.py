import ctypes
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable
ROOT_NAME = "软著"
DRAFT_NAME = "草稿"
FINAL_NAME = "申请资料"
OFFICECLI_MIN_VERSION = "1.0.151"
OFFICECLI_INSTALL_WIN = "irm https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.ps1 | iex"
OFFICECLI_INSTALL_POSIX = "curl -fsSL https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.sh | bash"
OFFICECLI_RELEASE = "https://github.com/iOfficeAI/OfficeCLI/releases"
CODE_FONT = "Consolas"
CODE_SIZE = "8pt"
CODE_SPACING = "13pt"
# 代码模式上下边距 1.8cm：(29.7cm-2×1.8cm)/13pt≈56.9，Word 实际每页容纳 56 行
CODE_LINES_PER_PAGE = 56
CODE_COLUMNS = 90
PAGE_TARGET = 60
EXCLUDE_DIRS = {".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__", "node_modules", "dist", "build", ".next", ".nuxt", ".output", "coverage", "target", "vendor", "venv", ".venv", "软件著作权申请资料", "软著材料", "软著", "softcopy-materials", "SoftwareCopyright-Skill"}
CONFIG_NAMES = {".babelrc", ".eslintrc", ".eslintrc.json", ".eslintrc.yaml", ".eslintrc.yml", ".prettierrc", ".prettierrc.json", ".swcrc", "angular.json", "astro.config.mjs", "astro.config.ts", "babel.config.js", "babel.config.json", "cargo.lock", "cargo.toml", "composer.json", "docker-compose.yaml", "docker-compose.yml", "eslint.config.cjs", "eslint.config.js", "eslint.config.mjs", "go.mod", "go.sum", "jsconfig.json", "lerna.json", "next.config.js", "next.config.mjs", "next.config.ts", "nuxt.config.js", "nuxt.config.ts", "nx.json", "package-lock.json", "package.json", "playwright.config.js", "playwright.config.ts", "postcss.config.cjs", "postcss.config.js", "prettier.config.cjs", "prettier.config.js", "project.json", "pyproject.toml", "rollup.config.js", "rollup.config.mjs", "svelte.config.js", "tailwind.config.js", "tailwind.config.ts", "tsconfig.app.json", "tsconfig.json", "tsconfig.node.json", "turbo.json", "vite.config.js", "vite.config.mjs", "vite.config.ts", "vitest.config.js", "vitest.config.ts", "webpack.config.js", "webpack.config.ts", "workspace.json", ".env.example"}
DOC_EXTS = {".adoc", ".doc", ".docx", ".md", ".odt", ".pdf", ".rst", ".rtf", ".txt", ".wps"}
BIN_EXTS = {".7z", ".a", ".avi", ".bin", ".bmp", ".class", ".db", ".dll", ".dmg", ".eot", ".exe", ".flac", ".gif", ".gz", ".ico", ".iso", ".jar", ".jpeg", ".jpg", ".lib", ".lockb", ".mov", ".mp3", ".mp4", ".o", ".obj", ".ogg", ".otf", ".pdb", ".png", ".pyc", ".rar", ".so", ".sqlite", ".sqlite3", ".tar", ".ttf", ".wav", ".webm", ".webp", ".woff", ".woff2", ".xls", ".xlsx", ".zip"}
NOISE_EXTS = {".csv", ".log", ".tsv"}
LOCK_NAMES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock"}
DOC_PREFIXES = ("readme", "license", "changelog", "contributing", "security", "code_of_conduct")
DOC_DIRNAMES = {"doc", "docs", "documentation", "spec", "specs", "设计文档", "需求文档"}
DOC_HINTS = ("prd", "brd", "architecture", "design", "manual", "requirement", "设计", "需求", "架构", "手册", "说明")
SOURCE_HINT_EXTS = {".vue", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".css", ".scss", ".sass", ".less", ".html", ".svelte", ".astro", ".c", ".cc", ".cpp", ".cs", ".cxx", ".dart", ".gd", ".gml", ".go", ".h", ".hh", ".hpp", ".java", ".kt", ".lua", ".php", ".ps1", ".py", ".rb", ".rs", ".sh", ".sql", ".swift", ".m", ".mm", ".zig", ".nim", ".ex", ".exs", ".erl", ".clj", ".scala", ".groovy", ".gradle", ".r", ".jl", ".v", ".sv"}
MAX_SOURCE_BYTES = 800000
ENTRY_BASENAMES = {"main.ts", "main.js", "main.tsx", "main.jsx", "index.tsx", "index.jsx", "app.vue", "app.vue".lower(), "app.tsx", "index.html", "manage.py", "app.py", "main.py", "__main__.py", "wsgi.py", "asgi.py"}
STYLE_EXTS = {".css", ".scss", ".sass", ".less"}
SEGMENT_WEIGHTS = (("router", 10), ("routes", 10), ("pages", 20), ("views", 20), ("screens", 20), ("api", 30), ("apis", 30), ("services", 30), ("controllers", 30), ("store", 40), ("stores", 40), ("pinia", 40), ("redux", 40), ("zustand", 40), ("models", 45), ("schemas", 45), ("entities", 45), ("components", 50), ("utils", 60), ("lib", 60), ("hooks", 60), ("composables", 60), ("helpers", 60), ("server", 70), ("backend", 70), ("workers", 70), ("handlers", 70))
PROSE_FILES = {"operation": ("操作手册.md", "操作手册自检.json", "操作手册自检.md", "_操作手册.docx"), "design": ("技术方案文档.md", "技术方案自检.json", "技术方案自检.md", "_技术方案.docx")}
CODE_DRAFTS = {"代码.md"}
STALE_CODE_DRAFTS = {"代码-前30页.md", "代码-后30页.md", "代码-全部.md"}
GATE_META_KEYS = {"user_confirmed", "gate_note", "confirmed_at", "content_sha256", "gate"}
SHOT_METHODS = ("agent-browser", "playwright-cli", "user-supplied", "skip")
HOST_TOOL_HINTS = {"browser": "可作为 agent-browser 截图方式，替代 Playwright CLI，图片仍必须落盘到 截图原始/", "playwright": "可执行 playwright-cli 自动截图", "pdf": "可读取无法自动提取正文的 PDF 证据，要点写入业务理解模型稿", "docx": "可预览和复核生成的正式 Word 文档", "word": "可预览和复核生成的正式 Word 文档", "vision": "可逐张查看渲染图，确认中文无乱码、无遮挡", "image": "可逐张查看渲染图，确认中文无乱码、无遮挡", "search": "可用于行业表达调研，但不得编造项目不存在的功能", "web": "可用于行业表达调研，但不得编造项目不存在的功能", "archify": "可作为宿主架构图技能：为业务理解声明的图纸插槽生成图片，落盘到 图纸原始/（文件名 01-插槽名.png，插槽名 architecture/key_N/function_N），figures.py 优先采用并登记图纸清单", "diagram": "可作为宿主架构图技能：为业务理解声明的图纸插槽生成图片，落盘到 图纸原始/（文件名 01-插槽名.png，插槽名 architecture/key_N/function_N），figures.py 优先采用并登记图纸清单"}
DOT_OPEN_RE = re.compile(r"\b(?:strict\s+)?(?:digraph|graph)(?:\s+\w+)?\s*\{")
DOT_LABEL_RE = re.compile(r"label\s*=\s*\"((?:[^\"\\]|\\.)*)\"")
DOT_QUOTED_RE = re.compile(r"\"((?:[^\"\\]|\\.)*)\"")
DOT_SLOT_RE = re.compile(r"^(architecture|key_[1-9][0-9]*|function_[1-9][0-9]*)$")
DIAGRAM_BACKENDS = ("dot-png", "dot-svg-cairosvg", "dot-svg-inkscape", "dot-svg-librsvg", "dot-svg-magick", "dot-svg-convert")
DIAGRAM_DPI = 150
CJK_FONT_FALLBACK = ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "Droid Sans Fallback")
DOT_LABEL_LIMIT = 24
def parse_semver(version: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version).strip())
    return (int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else None
def officecli_version_ok(version: str) -> bool:
    parsed = parse_semver(version)
    floor = parse_semver(OFFICECLI_MIN_VERSION)
    if parsed is None or floor is None:
        return False
    return parsed[0] == floor[0] and parsed >= floor
def officecli_version_requirement() -> str:
    return f"不低于 {OFFICECLI_MIN_VERSION} 且主版本为 {OFFICECLI_MIN_VERSION.split('.')[0]}"
def ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
def stop_for_user(action: str) -> None:
    print("STOP_FOR_USER")
    print(f"NEXT_ACTION: {action}")
    raise SystemExit(2)
def excluded_name(path: Path) -> bool:
    name = path.name
    if name in EXCLUDE_DIRS:
        return True
    if name.startswith(".") and name != ".env.example":
        return True
    if name in LOCK_NAMES:
        return True
    if name.endswith((".map", ".min.js", ".min.css")):
        return True
    return False
def iter_files(root: Path, exts: set[str] | None = None) -> Iterable[Path]:
    root = root.resolve()
    for base, dirs, names in os.walk(root):
        here = Path(base)
        dirs[:] = sorted(d for d in dirs if not excluded_name(here / d))
        for name in sorted(names):
            path = here / name
            if excluded_name(path):
                continue
            if exts is not None and path.suffix.lower() not in exts:
                continue
            yield path
def rel_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
def read_text(path: Path, limit: int | None = None) -> str:
    data = path.read_bytes()
    if limit is not None:
        data = data[:limit]
    encodings = ["utf-8", "utf-8-sig", "gb18030", "latin-1"]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.insert(0, "utf-16")
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        encodings.insert(0, "utf-32")
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
def load_json(path: Path) -> Any:
    return json.loads(read_text(path))
def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()
def payload_digest(data: dict[str, Any]) -> str:
    core = {key: value for key, value in data.items() if key not in GATE_META_KEYS}
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
def digest_current(data: dict[str, Any]) -> bool:
    expected = str(data.get("content_sha256") or "")
    return bool(expected) and expected == payload_digest(data)
def mark_confirmed(data: dict[str, Any], key: str, note: str) -> None:
    data[key] = True
    data["gate_note"] = note
    data["confirmed_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds")
    data["content_sha256"] = payload_digest(data)
def looks_binary(path: Path) -> bool:
    if path.suffix.lower() in BIN_EXTS:
        return True
    try:
        chunk = path.read_bytes()[:8192]
    except OSError:
        return True
    if not chunk:
        return False
    if chunk.startswith((b"PK\x03\x04", b"%PDF-", b"\x1f\x8b", b"\x89PNG", b"GIF8")):
        return True
    if chunk.startswith((b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return False
    if b"\x00" in chunk:
        return True
    hits = sum(1 for byte in chunk if byte < 32 and byte not in (9, 10, 12, 13))
    return hits / len(chunk) > 0.02
def is_config_name(path: Path) -> bool:
    return path.name in CONFIG_NAMES or path.name.lower() in CONFIG_NAMES
def is_source(path: Path) -> bool:
    if not path.is_file() or is_config_name(path):
        return False
    suffix = path.suffix.lower()
    if suffix in DOC_EXTS or suffix in BIN_EXTS or suffix in NOISE_EXTS:
        return False
    if path.name.lower().startswith(DOC_PREFIXES):
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size <= 0 or size > MAX_SOURCE_BYTES or looks_binary(path):
        return False
    try:
        sample = read_text(path, limit=20000)
    except Exception:
        return False
    if not sample.strip():
        return False
    if any(len(line) > 3000 for line in sample.splitlines()[:80]):
        return False
    return any(char.isalnum() for char in sample)
def is_doc(path: Path, root: Path | None = None) -> bool:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in DOC_EXTS or name.startswith(DOC_PREFIXES):
        return True
    try:
        display = Path(rel_posix(path, root)) if root is not None else path
    except ValueError:
        display = path
    parts = {part.lower() for part in display.parent.parts}
    hinted = any(hint in path.stem.lower() for hint in DOC_HINTS)
    return (bool(parts & DOC_DIRNAMES) or (hinted and suffix not in SOURCE_HINT_EXTS)) and not looks_binary(path)
def iter_sources(root: Path) -> Iterable[Path]:
    for path in iter_files(root):
        if is_source(path):
            yield path
def iter_docs(root: Path) -> Iterable[Path]:
    for path in iter_files(root):
        if is_doc(path, root):
            yield path
def category_weight(path: Path, root: Path) -> int:
    name = path.name.lower()
    if name in ENTRY_BASENAMES:
        return 0
    if path.suffix.lower() in STYLE_EXTS:
        return 90
    try:
        parts = Path(rel_posix(path, root)).parts[1:]
    except ValueError:
        parts = path.parts[1:]
    for part in parts:
        lowered = part.lower()
        for segment, weight in SEGMENT_WEIGHTS:
            if lowered == segment or lowered.startswith(segment + "."):
                return weight
    if path.suffix.lower() in SOURCE_HINT_EXTS:
        return 80
    return 85
def text_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)
def wrap_columns(line: str, limit: int = CODE_COLUMNS) -> list[str]:
    expanded = line.expandtabs(4)
    if not expanded:
        return [""]
    rows: list[str] = []
    buf = ""
    width = 0
    for char in expanded:
        cw = 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        if buf and width + cw > limit:
            rows.append(buf)
            buf = ""
            width = 0
        buf += char
        width += cw
    if buf:
        rows.append(buf)
    return rows
def _c_style(text: str) -> list[str]:
    kept_lines: list[str] = []
    in_block = False
    for line in text.splitlines():
        kept: list[str] = []
        quote: str | None = None
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            nxt = line[i + 1] if i + 1 < n else ""
            if in_block:
                if ch == "*" and nxt == "/":
                    in_block = False
                    i += 2
                else:
                    i += 1
                continue
            if quote:
                kept.append(ch)
                if ch == "\\" and nxt:
                    kept.append(nxt)
                    i += 2
                    continue
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in ("\"", "'", "`"):
                quote = ch
                kept.append(ch)
                i += 1
                continue
            if ch == "/" and nxt == "/":
                break
            if ch == "/" and nxt == "*":
                in_block = True
                i += 2
                continue
            kept.append(ch)
            i += 1
        cleaned = "".join(kept).rstrip()
        if cleaned.strip():
            kept_lines.append(cleaned)
    return kept_lines
def _hash_style(text: str) -> list[str]:
    kept_lines: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if fence:
            if fence in stripped:
                tail = stripped.split(fence, 1)[1].strip()
                fence = None
                if tail and not tail.startswith("#"):
                    kept_lines.append(tail)
            continue
        if stripped.startswith(('"""', "'''")):
            marker = stripped[:3]
            rest = stripped[3:]
            if marker in rest:
                tail = rest.split(marker, 1)[1].strip()
                if tail and not tail.startswith("#"):
                    kept_lines.append(tail)
            else:
                fence = marker
            continue
        if stripped.startswith("#"):
            continue
        kept: list[str] = []
        quote: str | None = None
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            nxt = line[i + 1] if i + 1 < n else ""
            if quote:
                kept.append(ch)
                if ch == "\\" and nxt:
                    kept.append(nxt)
                    i += 2
                    continue
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in ("\"", "'"):
                quote = ch
                kept.append(ch)
                i += 1
                continue
            if ch == "#":
                break
            kept.append(ch)
            i += 1
        cleaned = "".join(kept).rstrip()
        if cleaned.strip():
            kept_lines.append(cleaned)
    return kept_lines
def _dash_style(text: str) -> list[str]:
    kept_lines: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("--"):
            continue
        kept: list[str] = []
        in_quote = False
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            nxt = line[i + 1] if i + 1 < n else ""
            if in_quote:
                kept.append(ch)
                if ch == "'" and nxt == "'":
                    kept.append(nxt)
                    i += 2
                    continue
                if ch == "'":
                    in_quote = False
                i += 1
                continue
            if ch == "'":
                in_quote = True
                kept.append(ch)
                i += 1
                continue
            if ch == "-" and nxt == "-":
                break
            kept.append(ch)
            i += 1
        cleaned = "".join(kept).rstrip()
        if cleaned.strip():
            kept_lines.append(cleaned)
    return kept_lines
COMMENT_STYLE = {".py": "hash", ".sh": "hash", ".bash": "hash", ".zsh": "hash", ".rb": "hash", ".pl": "hash", ".pm": "hash", ".r": "hash", ".yaml": "hash", ".yml": "hash", ".toml": "hash", ".ini": "hash", ".conf": "hash", ".cfg": "hash", ".env": "hash", ".gd": "hash", ".tcl": "hash", ".cmake": "hash", ".mk": "hash", ".sql": "dash", ".lua": "dash", ".hs": "dash", ".elm": "dash"}
def comment_style(path: Path) -> str:
    return COMMENT_STYLE.get(path.suffix.lower(), "c")
def strip_comments(text: str, style: str) -> list[str]:
    if style == "hash":
        return _hash_style(text)
    if style == "dash":
        return _dash_style(text)
    return _c_style(text)
def material_lines(text: str, style: str, limit: int = CODE_COLUMNS) -> list[str]:
    rows: list[str] = []
    for source_line in strip_comments(text, style):
        rows.extend(wrap_columns(source_line, limit))
    return rows
def manual_kind_of(draft_dir: Path) -> str:
    path = draft_dir / "业务理解.json"
    if not path.is_file():
        return "operation"
    try:
        data = load_json(path)
    except Exception:
        return "operation"
    return "design" if isinstance(data, dict) and data.get("manual_kind") == "design" else "operation"
def draft_snapshot(workdir: Path) -> dict[str, str]:
    draft_dir = workdir / DRAFT_NAME
    snapshot: dict[str, str] = {}
    if not draft_dir.is_dir():
        return snapshot
    paths = [p for p in sorted(draft_dir.rglob("*")) if p.is_file() and p.name != "最终确认.json" and p.suffix.lower() in (".md", ".json")]
    manifest = workdir / "截图" / "截图清单.json"
    if manifest.is_file():
        paths.append(manifest)
        try:
            for entry in load_json(manifest).get("screenshots") or []:
                if isinstance(entry, dict) and entry.get("path"):
                    image = Path(str(entry["path"]))
                    if not image.is_absolute():
                        image = manifest.parent / image
                    if image.is_file():
                        paths.append(image.resolve())
        except Exception:
            pass
    figure_manifest = draft_dir / "图纸清单.json"
    if figure_manifest.is_file():
        try:
            for entry in load_json(figure_manifest).get("figures") or []:
                if isinstance(entry, dict) and entry.get("path"):
                    image = Path(str(entry["path"]))
                    if not image.is_absolute():
                        image = figure_manifest.parent / image
                    if image.is_file():
                        paths.append(image.resolve())
        except Exception:
            pass
    base = workdir.resolve()
    for index, path in enumerate(paths, start=1):
        resolved = path.resolve()
        try:
            key = resolved.relative_to(base).as_posix()
        except ValueError:
            key = f"external/{index}-{resolved.name}"
        snapshot[key] = sha256_file(resolved)
    return snapshot
REVIEW_DIR_NAME = "审查"
REVIEW_DRAFT_NAME = "合规审查底稿"
REVIEW_REPORT_NAME = "审查报告.md"
REVIEW_GATE_NAME = "合规审查确认.json"
REVIEW_VERDICT_PASS = "通过"
REVIEW_VERDICT_ADVISORY = "整改后通过"
REVIEW_VERDICT_FAIL = "不通过"
REVIEW_VERDICTS = (REVIEW_VERDICT_PASS, REVIEW_VERDICT_ADVISORY, REVIEW_VERDICT_FAIL)
REVIEW_GATE_KEY = "review_confirmed"
REVIEW_GATE_META_KEYS = GATE_META_KEYS | {REVIEW_GATE_KEY}
def review_dir_of(workdir: Path) -> Path:
    return workdir / REVIEW_DIR_NAME
def review_report_of(workdir: Path) -> Path:
    return review_dir_of(workdir) / REVIEW_REPORT_NAME
def review_gate_of(workdir: Path) -> Path:
    return review_dir_of(workdir) / REVIEW_GATE_NAME
def final_snapshot(workdir: Path) -> dict[str, str]:
    """正式交付物与审查报告的内容指纹，用于审查门禁的失效判定。

    只纳入真正需要用户重新认可的两类产物：
    - 申请资料/ 下的正式文件（提交给版权局的实体）；
    - 审查/审查报告.md（模型出具的审查结论）。
    不含 合规审查底稿（机器每次重跑都带新时间戳，纳入会产生无意义失效）。
    """
    snapshot: dict[str, str] = {}
    base = workdir.resolve()
    paths: list[Path] = []
    final_root = workdir / FINAL_NAME
    if final_root.is_dir():
        paths.extend(path for path in sorted(final_root.rglob("*")) if path.is_file())
    report = review_report_of(workdir)
    if report.is_file():
        paths.append(report)
    for index, path in enumerate(paths, start=1):
        resolved = path.resolve()
        try:
            key = resolved.relative_to(base).as_posix()
        except ValueError:
            key = f"external/{index}-{resolved.name}"
        snapshot[key] = sha256_file(resolved)
    return snapshot
REVIEW_VERDICT_PATTERN = re.compile(
    r"审查结论\s*\*?\s*[：:]\s*\**\s*(整改后通过|不通过|通过)\s*(?:[（(\*。,，；;、]|$)"
)
REVIEW_VERDICT_HEADING = re.compile(r"^#{1,6}\s*(?:[零一二三四五六七八九十\d]+[、.]\s*)?\*?\s*审查结论\s*\*?\s*$")
REVIEW_VERDICT_STANDALONE = re.compile(r"^\**\s*(整改后通过|不通过|通过)\s*\**\s*[。]?$")
def review_verdict_of(text: str) -> str:
    """从审查报告中提取审查结论。

    只认明确写出的结论，不从正文措辞猜测：
    - 行内形式：`审查结论：通过`
    - 标题形式：`## 审查结论` 后紧跟一行只有结论词

    匹配时长的结论词优先，避免「不通过」被误判成「通过」。
    """
    if not text:
        return ""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = REVIEW_VERDICT_PATTERN.search(line)
        if match:
            return match.group(1)
        if REVIEW_VERDICT_HEADING.match(line.strip()):
            for follow in lines[index + 1: index + 6]:
                candidate = follow.strip()
                if not candidate:
                    continue
                standalone = REVIEW_VERDICT_STANDALONE.match(candidate)
                if standalone:
                    return standalone.group(1)
                break
    return ""
def review_verdict_issues(workdir: Path) -> list[str]:
    """审查门禁前置检查：报告缺失或结论不合格时给出具体问题。"""
    issues: list[str] = []
    report = review_report_of(workdir)
    if not report.is_file():
        issues.append(f"缺少 {REVIEW_REPORT_NAME}；请先完成审查并出具报告")
        return issues
    text = read_text(report)
    if not text.strip():
        issues.append(f"{REVIEW_REPORT_NAME} 为空")
        return issues
    verdict = review_verdict_of(text)
    if not verdict:
        issues.append(f"{REVIEW_REPORT_NAME} 未在「审查结论」段落明确写出结论（{'/'.join(REVIEW_VERDICTS)}）")
    return issues
def draft_completeness_issues(workdir: Path) -> list[str]:
    draft_dir = workdir / DRAFT_NAME
    kind = manual_kind_of(draft_dir)
    doc_md, review_json, review_md, _suffix = PROSE_FILES[kind]
    required = ["业务理解.md", "业务理解.json", "代码文件选择.json", "代码提取清单.md", "代码提取清单.json", "申请表信息.md", doc_md, review_md, review_json]
    issues = [f"缺少 {DRAFT_NAME}/{name}" for name in required if not (draft_dir / name).is_file()]
    other_md = PROSE_FILES["design" if kind == "operation" else "operation"][0]
    if (draft_dir / other_md).is_file():
        issues.append(f"存在与当前文档类型冲突的旧草稿：{other_md}")
    manifest_path = draft_dir / "代码提取清单.json"
    if not manifest_path.is_file():
        return issues
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        return issues + [f"代码提取清单.json 无法读取：{exc}"]
    outputs = manifest.get("outputs") if isinstance(manifest, dict) else None
    if not isinstance(outputs, list) or not outputs:
        return issues + ["代码提取清单.json 未声明代码 Markdown 输出"]
    declared = {str(name) for name in outputs}
    invalid = sorted(declared - CODE_DRAFTS)
    if invalid:
        issues.append("代码提取清单包含未知输出：" + "、".join(invalid))
    for name in sorted(declared & CODE_DRAFTS):
        if not (draft_dir / name).is_file():
            issues.append(f"缺少清单声明的 草稿/{name}")
    stale = sorted(name for name in (CODE_DRAFTS | STALE_CODE_DRAFTS) - declared if (draft_dir / name).exists())
    if stale:
        issues.append("存在与当前提取模式冲突的旧草稿：" + "、".join(stale))
    review_path = draft_dir / review_json
    if review_path.is_file():
        try:
            rounds = load_json(review_path).get("rounds") or []
            if rounds and isinstance(rounds[-1].get("blocking"), list) and rounds[-1]["blocking"]:
                issues.append(f"{doc_md} 自检仍有未解决问题：" + "；".join(str(item) for item in rounds[-1]["blocking"][:5]))
        except Exception as exc:
            issues.append(f"{review_json} 无法读取：{exc}")
    return issues
def safe_name(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    return cleaned or "软件"
def cjk_font() -> str | None:
    if os.name == "nt":
        return "Microsoft YaHei"
    darwin = sys.platform == "darwin"
    try:
        done = subprocess.run(["fc-list", ":lang=zh", "family"], capture_output=True, text=True, timeout=20, check=False)
        if done.returncode == 0:
            have = {line.strip() for line in done.stdout.splitlines() if line.strip()}
            if not have:
                return None
            preferences = ("PingFang SC", "Hiragino Sans GB", "Heiti SC") + CJK_FONT_FALLBACK if darwin else CJK_FONT_FALLBACK
            for font in preferences:
                if font in have:
                    return font
            return sorted(have)[0]
    except (OSError, subprocess.SubprocessError):
        pass
    return "PingFang SC" if darwin else None
def normalize_dot(src: str) -> str:
    match = DOT_OPEN_RE.search(src)
    if not match:
        return src
    font = cjk_font() or "sans-serif"
    has_labeled_edge = bool(re.search(r"->[^;\]]*\[[^\]]*label\s*=", src))
    own_splines = bool(re.search(r"\bsplines\s*=", src))
    spline = "polyline" if has_labeled_edge and not own_splines else "ortho"
    head = (f'graph [rankdir=TB, nodesep=0.5, ranksep=0.8, splines={spline}, fontname="{font}", fontsize=12, bgcolor="white", pad="0.3", labeljust=l];\n'
            f'node [shape=box, style="rounded,filled", fillcolor="#F5F7FA", color="#4A6FA5", fontname="{font}", fontsize=12, width=2.2, margin="0.18,0.1"];\n'
            f'edge [color="#4A6FA5", fontname="{font}", fontsize=10, arrowsize=0.7];')
    return src[: match.end()] + "\n" + head + src[match.end():]
def _label_lines(value: str) -> list[str]:
    return re.split(r"\\[nlr]", value)
def lint_dot(src: str) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    advisory: list[str] = []
    cleaned = re.sub(r"/\*.*?\*/", "", re.sub(r"//[^\n]*", "", src))
    for match in DOT_LABEL_RE.finditer(cleaned):
        for line in _label_lines(match.group(1)):
            if len(line) > DOT_LABEL_LIMIT:
                blocking.append(f"标签单行 {len(line)} 字超过 {DOT_LABEL_LIMIT} 字上限，会撑宽节点造成遮挡：{line[:16]}…")
                break
    for match in DOT_QUOTED_RE.finditer(cleaned):
        prefix = cleaned[max(0, match.start() - 12): match.start()]
        if re.search(r"=\s*$", prefix):
            continue
        for line in _label_lines(match.group(1)):
            if len(line) > DOT_LABEL_LIMIT:
                blocking.append(f"节点名单行 {len(line)} 字超过 {DOT_LABEL_LIMIT} 字上限：{line[:16]}…")
                break
    edges = len(re.findall(r"->", cleaned))
    if edges > 12:
        advisory.append(f"连线 {edges} 条偏多，建议按层拆图或减少跨层连线")
    if len(DOT_LABEL_RE.findall(cleaned)) > 4:
        advisory.append("边标签超过 4 处，容易与节点重叠，建议移到正文说明")
    if not re.search(r"\bsplines\s*=", cleaned):
        advisory.append("未显式指定 splines，建议 splines=ortho 保证走线整齐")
    return blocking, advisory
def png_size(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            head = handle.read(33)
        if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", head[16:24])
    except OSError:
        return None
def png_layout_issues(path: Path, allow_wide: bool = False) -> list[str]:
    size = png_size(path)
    if size is None:
        return ["PNG 无法读取，布局无法校验"]
    width, height = size
    if width == 0 or height == 0:
        return ["PNG 尺寸异常"]
    ratio = width / height
    if allow_wide:
        if ratio > 6:
            return [f"横向图过于扁平（{width}×{height}），插入竖版文档后文字不可读，建议 rankdir=TB 或拆分"]
        if ratio < 0.2:
            return [f"图片宽高比失衡（{width}×{height}），纵向拉得过长"]
        return []
    if ratio > 3.5 or ratio < 1 / 3.5:
        return [f"图片宽高比失衡（{width}×{height}，比值 {ratio:.1f}），建议调整分层"]
    return []
def _run_ok(command: list[str], *, stdin: bytes | None = None, stdout_path: Path | None = None, timeout: int = 120) -> bool:
    try:
        if stdout_path is not None:
            with stdout_path.open("wb") as handle:
                done = subprocess.run(command, input=stdin, stdout=handle, stderr=subprocess.PIPE, timeout=timeout, check=False)
        else:
            done = subprocess.run(command, input=stdin, capture_output=True, timeout=timeout, check=False)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
def _module_exists(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None
def detect_diagram_backends() -> dict[str, Any]:
    dot = shutil.which("dot")
    if not dot:
        return {"available": False, "backend": "none", "backends": [], "detail": "未安装 graphviz（dot 命令不可用）；图纸将以中文文本框线图输出"}
    probe = Path(__import__("tempfile").mkdtemp(prefix="softcopy-probe-"))
    backends: list[str] = []
    try:
        png = probe / "probe.png"
        if _run_ok([dot, "-Tpng"], stdin="digraph G { 图 -> 纸; }".encode("utf-8"), stdout_path=png) and png.is_file() and png.stat().st_size > 0:
            backends.append("dot-png")
        svg = probe / "probe.svg"
        if _run_ok([dot, "-Tsvg"], stdin="digraph G { 图 -> 纸; }".encode("utf-8"), stdout_path=svg) and svg.is_file() and svg.stat().st_size > 0:
            converters: list[tuple[str, list[str]]] = []
            if _module_exists("cairosvg"):
                converters.append(("cairosvg", [sys.executable, "-m", "cairosvg"]))
            if shutil.which("inkscape"):
                converters.append(("inkscape", ["inkscape"]))
            if shutil.which("rsvg-convert"):
                converters.append(("librsvg", ["rsvg-convert"]))
            if shutil.which("magick"):
                converters.append(("magick", ["magick"]))
            if shutil.which("convert"):
                converters.append(("convert", ["convert"]))
            for name, _cmd in converters:
                out = probe / f"probe-{name}.png"
                if name == "cairosvg":
                    ok = _run_ok([sys.executable, "-m", "cairosvg", str(svg), "-o", str(out)])
                elif name == "inkscape":
                    ok = _run_ok(["inkscape", str(svg), "-o", str(out)])
                elif name == "librsvg":
                    ok = _run_ok(["rsvg-convert", "-o", str(out), str(svg)])
                else:
                    ok = _run_ok([name, str(svg), str(out)])
                if ok and out.is_file() and out.stat().st_size > 0:
                    backends.append(f"dot-svg-{name}")
        if not backends:
            return {"available": False, "backend": "none", "backends": [], "detail": "graphviz 已安装但 PNG/SVG 输出链不可用；图纸将以中文文本框线图输出"}
        return {"available": True, "backend": backends[0], "backends": backends, "detail": "可用渲染链：" + "、".join(backends)}
    finally:
        shutil.rmtree(probe, ignore_errors=True)
def graphviz_install_hint() -> str:
    if os.name == "nt":
        return "winget install graphviz（或 choco install graphviz / scoop install graphviz）"
    if sys.platform == "darwin":
        return "brew install graphviz"
    return "sudo apt install graphviz（或使用对应发行版包管理器）"
def find_chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        hit = shutil.which(name)
        if hit:
            return hit
    if os.name == "nt":
        bases = [os.environ.get("PROGRAMFILES"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")]
        for base in bases:
            if base:
                candidate = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
                if candidate.is_file():
                    return str(candidate)
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("ProgramFiles(x86)")):
            if base:
                candidate = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
                if candidate.is_file():
                    return str(candidate)
    if sys.platform == "darwin":
        candidate = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if candidate.is_file():
            return str(candidate)
    return None
def memory_gb() -> int | None:
    if os.name == "nt":
        try:
            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong), ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong), ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong), ("avail_extended", ctypes.c_ulonglong)]
            status = Status()
            status.length = ctypes.sizeof(Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_phys // (1024 ** 3))
        except Exception:
            return None
        return None
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // (1024 ** 3))
    except (AttributeError, OSError, ValueError):
        return None
def disk_gb() -> int | None:
    try:
        return int(shutil.disk_usage(Path.home()).total // (1024 ** 3))
    except OSError:
        return None
def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
