import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
import common as C
THEME_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
THEME_TARGETS = {"major.latin": "Times New Roman", "major.ea": "SimSun", "major.cs": "Times New Roman", "minor.latin": "Times New Roman", "minor.ea": "SimSun", "minor.cs": "Times New Roman"}
PLACEHOLDER_RE = re.compile(r"【截图预留：([^】]*)】")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
SHOT_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
class OfficeCliError(RuntimeError):
    pass
def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env["OFFICECLI_SKIP_UPDATE"] = "1"
    env["OFFICECLI_NO_AUTO_RESIDENT"] = "1"
    return env
def resolve_officecli() -> Path | None:
    for name in ("officecli", "officecli.exe"):
        hit = shutil.which(name)
        if hit and Path(hit).is_file():
            return Path(hit).resolve()
    return None
class OfficeCli:
    def __init__(self, strict_version: bool = True) -> None:
        executable = resolve_officecli()
        if executable is None:
            raise OfficeCliError(f"当前进程找不到全局 officecli；请按官方方式全局安装满足版本要求（{C.officecli_version_requirement()}）的 officecli 并重启 coding agent。")
        self.executable = executable
        self.version = self._version()
        if strict_version and not C.officecli_version_ok(self.version):
            raise OfficeCliError(f"OfficeCLI 版本不匹配：{self.version}，要求 {C.officecli_version_requirement()}；如用户已明确承担风险可传 --allow-untested-officecli。")
    def _run(self, args: list[str], *, timeout: int = 120, expect_json: bool = True, check: bool = True) -> dict[str, Any]:
        done = subprocess.run([str(self.executable), *args], text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout, check=False, env=cli_env())
        combined = "\n".join(part for part in (done.stdout, done.stderr) if part).strip()
        payload = self._parse_json(combined) if expect_json else {"raw": combined}
        failed = isinstance(payload, dict) and payload.get("success") is False
        if check and (done.returncode != 0 or failed):
            detail = payload.get("error") if isinstance(payload, dict) else None
            raise OfficeCliError(f"OfficeCLI 命令失败：{' '.join(args[:3])}\n{detail or combined}")
        payload.setdefault("returncode", done.returncode)
        return payload
    def _parse_json(self, text: str) -> dict[str, Any]:
        if not text.strip():
            return {}
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                value, _ = decoder.raw_decode(text[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return {"raw": text}
    def _version(self) -> str:
        result = self._run(["--version"], expect_json=False)
        raw = str(result.get("raw", "")).strip()
        match = re.search(r"\d+\.\d+\.\d+", raw)
        return match.group(0) if match else raw or "unknown"
    def create(self, output: Path, commands: list[dict[str, Any]]) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self._run(["create", str(output.resolve()), "--force", "--locale", "zh-CN", "--json"])
        self.run_batch(output, commands)
    def run_batch(self, output: Path, commands: list[dict[str, Any]]) -> None:
        if not commands:
            return
        batch: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".batch.json", prefix=f".{output.stem}-", dir=output.parent, encoding="utf-8", delete=False) as handle:
                json.dump(commands, handle, ensure_ascii=False, indent=1)
                batch = Path(handle.name)
            args = ["batch", str(output.resolve()), "--input", str(batch), "--stop-on-error", "--json"]
            timeout = max(120, min(900, 60 + len(commands) // 8))
            last: OfficeCliError | None = None
            for delay in (0.0, 0.3, 1.0):
                if delay:
                    time.sleep(delay)
                try:
                    self._run(args, timeout=timeout)
                    return
                except OfficeCliError as exc:
                    last = exc
                    if "io_error" not in str(exc):
                        raise
            raise last or OfficeCliError("batch 未知失败")
        finally:
            if batch:
                batch.unlink(missing_ok=True)
    def get(self, output: Path, path: str) -> dict[str, Any]:
        return self._run(["get", str(output.resolve()), path, "--json"])
    def raw(self, output: Path, part: str) -> dict[str, Any]:
        return self._run(["raw", str(output.resolve()), part, "--json"], timeout=180)
    def raw_set(self, output: Path, part: str, xpath: str, action: str, xml: str) -> dict[str, Any]:
        return self._run(["raw-set", str(output.resolve()), part, "--xpath", xpath, "--action", action, "--xml", xml, "--json"], timeout=180)
    def validate(self, output: Path) -> dict[str, Any]:
        return self._run(["validate", str(output.resolve()), "--json"], timeout=180)
    def issues(self, output: Path) -> dict[str, Any]:
        return self._run(["view", str(output.resolve()), "issues", "--json"], timeout=180)
    def stats(self, output: Path, *, page_count: bool = False) -> dict[str, Any]:
        args = ["view", str(output.resolve()), "stats"]
        if page_count:
            args.append("--page-count")
        args.append("--json")
        return self._run(args, timeout=300, check=not page_count)
    def screenshot(self, output: Path, target: Path) -> dict[str, Any]:
        target.parent.mkdir(parents=True, exist_ok=True)
        return self._run(["view", str(output.resolve()), "screenshot", "--grid", "auto", "--render", "auto", "--out", str(target.resolve()), "--json"], timeout=300, expect_json=False)
def data_of(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("data") if isinstance(payload, dict) else None
    return value if isinstance(value, dict) else {}
def count_of(payload: dict[str, Any]) -> int:
    try:
        return int(data_of(payload).get("count", 0))
    except (TypeError, ValueError):
        return 0
def header_commands(software_name: str, version: str) -> list[dict[str, Any]]:
    header_path = "/header[1]/p[1]"
    return [
        {"command": "add", "parent": "/", "type": "header", "props": {"type": "default", "text": f"{software_name} {version}", "align": "left", "font": "SimSun", "size": "9pt", "color": "#000000"}},
        {"command": "add", "parent": header_path, "type": "ptab", "props": {"align": "right", "relativeTo": "margin", "leader": "none"}},
        {"command": "add", "parent": header_path, "type": "run", "props": {"text": "第 ", "font": "SimSun", "size": "9pt", "color": "#000000"}},
        {"command": "add", "parent": header_path, "type": "field", "props": {"fieldType": "page", "font": "SimSun", "size": "9pt", "color": "#000000"}},
        {"command": "add", "parent": header_path, "type": "run", "props": {"text": " 页", "font": "SimSun", "size": "9pt", "color": "#000000"}},
    ]
def document_commands(software_name: str, version: str, *, code_mode: bool) -> list[dict[str, Any]]:
    margin = "1.8cm" if code_mode else "2.5cm"
    return [
        {"command": "set", "path": "/", "props": {"docDefaults.font": "SimSun", "docDefaults.font.eastAsia": "SimSun", "docDefaults.font.hAnsi": "Times New Roman", "docDefaults.fontSize": C.CODE_SIZE if code_mode else "10.5pt", "docDefaults.color": "#000000", "updateFields": "true", "title": f"{software_name} {version}"}},
        {"command": "set", "path": "/section[1]", "props": {"pageWidth": "21cm", "pageHeight": "29.7cm", "orientation": "portrait", "marginTop": margin, "marginBottom": margin, "marginLeft": margin, "marginRight": margin, "marginHeader": "0.9cm", "marginFooter": "0.9cm", "pageStart": "1"}},
        *header_commands(software_name, version),
    ]
def parse_code_pages(md_path: Path) -> list[tuple[int, list[str]]]:
    raw_pages: list[tuple[int, list[str]]] = []
    current: int | None = None
    rows: list[str] = []
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^##\s+第\s*(\d+)\s*页", raw.strip())
        if match:
            if current is not None:
                raw_pages.append((current, rows))
            current = int(match.group(1))
            rows = []
            continue
        if current is not None:
            rows.append(raw)
    if current is not None:
        raw_pages.append((current, rows))
    pages: list[tuple[int, list[str]]] = []
    for number, block in raw_pages:
        body = list(block)
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        if body and body[0].lstrip().startswith("```"):
            body.pop(0)
            while body and not body[0].strip():
                body.pop(0)
        if body and body[-1].strip().startswith("```"):
            body.pop()
            while body and not body[-1].strip():
                body.pop()
        pages.append((number, body))
    return pages
def rename_template_names(text: str, old: str, new: str, kind: str, version: str) -> tuple[str, int]:
    if not old or old == new:
        return text, 0
    pairs = [(f"# {old}操作手册", f"# {new}操作手册"), (f"以上要求用于保障{old}正常打开页面", f"以上要求用于保障{new}正常打开页面")]
    if kind == "design":
        pairs = [(f"# {old}技术方案文档", f"# {new}技术方案文档"), (f"本文档是对{old} ", f"本文档是对{new} "), (f"{old} {version}主要有以下功能", f"{new} {version}主要有以下功能")]
    total = text.count(old)
    replaced = 0
    for before, after in pairs:
        replaced += text.count(before) * before.count(old)
        text = text.replace(before, after)
    return text, max(total - replaced, 0)
def prose_page_warning(pages: int | None, name: str) -> str | None:
    if pages is None:
        return "当前环境无法读取文档 Word 原生页数；提交前请在 Word/WPS 复核文档鉴别材料页数（应不超过 60 页）"
    if pages > C.PAGE_TARGET:
        return f"{name} Word 自动分页 {pages} 页；文档鉴别材料按《计算机软件著作权登记办法》第十条应提交前 30 页 + 后 30 页（共 60 页），请压缩文档或按前 30 页 + 后 30 页截取后再提交"
    return None
def build_code_docx(cli: OfficeCli, md_path: Path, out_path: Path, software_name: str, version: str) -> int:
    pages = parse_code_pages(md_path)
    if not pages:
        raise OfficeCliError(f"代码草稿没有可识别分页：{md_path}")
    commands = document_commands(software_name, version, code_mode=True)
    for _number, rows in pages:
        for row in rows:
            commands.append({"command": "add", "parent": "/body", "type": "paragraph", "props": {"text": row if row else " ", "font": C.CODE_FONT, "font.ea": "SimSun", "size": C.CODE_SIZE, "color": "#000000", "spaceBefore": "0pt", "spaceAfter": "0pt", "lineSpacing": C.CODE_SPACING, "lineRule": "exact", "widowControl": "false", "wordWrap": "false"}})
    expected = sum(len(rows) for _n, rows in pages)
    actual = -1
    for attempt in range(2):
        cli.create(out_path, commands)
        normalize_theme(cli, out_path)
        try:
            actual = int(data_of(cli.stats(out_path)).get("paragraphs", -1))
        except (TypeError, ValueError):
            actual = -1
        if actual == expected:
            return len(pages)
        if attempt == 0:
            time.sleep(0.5)
    raise OfficeCliError(f"{out_path.name} 正文完整性校验失败：草稿 {expected} 个物理行，DOCX 实际 {actual} 个段落")
def normalize_theme(cli: OfficeCli, output: Path) -> None:
    payload = cli.raw(output, "/theme")
    theme_xml = payload.get("data") if isinstance(payload, dict) else ""
    if not isinstance(theme_xml, str) or not theme_xml.strip():
        raise OfficeCliError("OfficeCLI 未返回可读取的主题 XML")
    normalized = normalize_theme_xml(theme_xml)
    cli.raw_set(output, "/theme", "/a:theme", "replace", normalized)
    verify_theme(cli, output)
def normalize_theme_xml(theme_xml: str) -> str:
    root = ET.fromstring(theme_xml)
    ns = {"a": THEME_NS}
    for family in ("major", "minor"):
        parent = root.find(f".//a:{family}Font", ns)
        if parent is None:
            raise OfficeCliError(f"主题缺少 {family}Font")
        for node in list(parent):
            if node.tag == f"{{{THEME_NS}}}font":
                parent.remove(node)
    for slot, typeface in THEME_TARGETS.items():
        family, script = slot.split(".", 1)
        node = root.find(f".//a:{family}Font/a:{script}", ns)
        if node is None:
            raise OfficeCliError(f"主题缺少 {family}Font/{script}")
        node.set("typeface", typeface)
    ET.register_namespace("a", THEME_NS)
    return ET.tostring(root, encoding="unicode")
def theme_slots(theme_xml: str) -> dict[str, str]:
    root = ET.fromstring(theme_xml)
    ns = {"a": THEME_NS}
    slots: dict[str, str] = {}
    for family in ("major", "minor"):
        parent = root.find(f".//a:{family}Font", ns)
        if parent is None:
            raise OfficeCliError(f"主题缺少 {family}Font")
        for script in ("latin", "ea", "cs"):
            node = parent.find(f"a:{script}", ns)
            if node is None:
                raise OfficeCliError(f"主题缺少 {family}Font/{script}")
            slots[f"{family}.{script}"] = node.get("typeface", "")
    return slots
def verify_theme(cli: OfficeCli, output: Path) -> None:
    payload = cli.raw(output, "/theme")
    theme_xml = str(payload.get("data") or "")
    slots = theme_slots(theme_xml)
    bad = {slot: value for slot, value in slots.items() if value != THEME_TARGETS[slot]}
    if bad:
        detail = "，".join(f"{s}={v or '空'}" for s, v in bad.items())
        raise OfficeCliError(f"{output.name} 主题字体校验失败：{detail}")
def resolve_shot_path(raw_path: str, workdir: Path, manifest_path: Path) -> Path | None:
    source = Path(raw_path)
    candidates = [source] if source.is_absolute() else [Path.cwd() / source, workdir / source, workdir.parent / source, manifest_path.parent / source, manifest_path.parent / source.name]
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() in SHOT_EXTS:
            return candidate.resolve()
    return None
def shot_paths(manifest_path: Path, workdir: Path) -> tuple[list[Path | None], list[str]]:
    if not manifest_path.is_file():
        return [], []
    entries = C.load_json(manifest_path).get("screenshots") or []
    paths: list[Path | None] = []
    warnings: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or not str(entry.get("path") or "").strip():
            warnings.append(f"截图清单第 {index} 项无效，未插入")
            paths.append(None)
            continue
        resolved = resolve_shot_path(str(entry["path"]), workdir, manifest_path)
        if resolved is None:
            warnings.append(f"截图清单第 {index} 项文件不存在或格式不支持")
        paths.append(resolved)
    return paths, warnings
def prepare_manual_markdown(md_path: Path, base_dir: Path, output: Path, shots: list[Path | None]) -> tuple[str, list[dict[str, Any]], int]:
    text = md_path.read_text(encoding="utf-8")
    images: list[dict[str, Any]] = []
    def register(path: Path, alt: str, origin: str) -> str:
        placeholder = f"SOFTCOPY_IMG_{len(images) + 1:04d}"
        images.append({"placeholder": placeholder, "path": path, "alt": alt, "origin": origin})
        return f"\n\n{placeholder}\n\n"
    def replace_image(match: re.Match[str]) -> str:
        alt = match.group(1).strip() or "插图"
        target = match.group(2).strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
            return f"\n\n【远程图片未嵌入：{alt}（{target}）】\n\n"
        path = (base_dir / target).resolve()
        if not path.is_file():
            return f"\n\n【图片缺失：{target}】\n\n"
        return register(path, alt, "markdown")
    text = IMAGE_RE.sub(replace_image, text)
    iterator = iter(shots)
    def replace_shot(match: re.Match[str]) -> str:
        try:
            path = next(iterator)
        except StopIteration:
            return match.group(0)
        if path is None:
            return match.group(0)
        alt = match.group(1).strip().rstrip("。") or "操作截图"
        return register(path, alt, "manifest")
    remaining = len(PLACEHOLDER_RE.findall(text))
    text = PLACEHOLDER_RE.sub(replace_shot, text)
    output.write_text(text, encoding="utf-8")
    return text, images, remaining
def body_children(cli: OfficeCli, output: Path) -> list[dict[str, Any]]:
    for result in data_of(cli.get(output, "/body")).get("results", []):
        if isinstance(result, dict) and result.get("path") == "/body":
            children = result.get("children")
            return children if isinstance(children, list) else []
    return []
def manual_format_commands(children: list[dict[str, Any]], images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_placeholder = {item["placeholder"]: item for item in images}
    commands: list[dict[str, Any]] = []
    for child in children:
        if child.get("type") != "paragraph" or not child.get("path"):
            continue
        path = str(child["path"])
        text = str(child.get("text") or "")
        style = str(child.get("style") or (child.get("format") or {}).get("style") or "")
        fmt = child.get("format") if isinstance(child.get("format"), dict) else {}
        if text in by_placeholder:
            image = by_placeholder[text]
            commands.append({"command": "set", "path": path, "props": {"text": "", "align": "center"}})
            commands.append({"command": "add", "parent": path, "type": "picture", "props": {"src": str(image["path"]), "width": "15cm", "alt": str(image["alt"])}})
            continue
        props: dict[str, str] = {"font": "SimSun", "font.ea": "SimSun", "color": "#000000", "spaceAfter": "6pt", "lineSpacing": "1.5x", "widowControl": "true"}
        if style.lower().startswith("heading"):
            props.update({"font": "SimHei", "font.ea": "SimHei", "keepNext": "true"})
        elif fmt.get("listStyle"):
            props.update({"size": "10.5pt", "align": "left"})
        elif text.startswith("【截图") or text.startswith("【图预留") or text.startswith("【图片缺失") or text.startswith("【远程图片"):
            props.update({"size": "10.5pt", "align": "center"})
        else:
            props.update({"size": "10.5pt", "align": "justify", "firstLineChars": "200"})
        commands.append({"command": "set", "path": path, "props": props})
    return commands
def build_manual_docx(cli: OfficeCli, md_path: Path, out_path: Path, base_dir: Path, software_name: str, version: str, shots: list[Path | None]) -> dict[str, int]:
    prepared: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", prefix=".softcopy-manual-", dir=out_path.parent, encoding="utf-8", delete=False) as handle:
            prepared = Path(handle.name)
        _text, images, remaining = prepare_manual_markdown(md_path, base_dir, prepared, shots)
        commands = document_commands(software_name, version, code_mode=False)
        commands.append({"command": "add", "parent": "/", "type": "markdown", "props": {"src": str(prepared.resolve())}})
        cli.create(out_path, commands)
        cli.run_batch(out_path, manual_format_commands(body_children(cli, out_path), images))
        normalize_theme(cli, out_path)
        used = sum(1 for item in images if item["origin"] == "manifest")
        unused = max(0, sum(1 for p in shots if p is not None) - used)
        return {"inserted": used, "remaining_placeholders": remaining, "unused_images": unused}
    finally:
        if prepared:
            prepared.unlink(missing_ok=True)
def field_value(md_path: Path, field: str) -> str:
    prefix = f"➤{field}："
    for line in md_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return ""
def write_application_txt(md_path: Path, out_path: Path, page_override: int | None) -> tuple[Path, list[str]]:
    fields: list[str] = []
    warnings: list[str] = []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("➤"):
            continue
        if page_override is not None and stripped.startswith("➤页数："):
            old = stripped[len("➤页数："):]
            if old.isdigit() and int(old) != page_override:
                warnings.append(f"申请表页数已按 Word 实际分页由 {old} 修正为 {page_override}")
            stripped = f"➤页数：{page_override}"
        if "待确认" in stripped:
            warnings.append(f"申请表仍含待确认字段：{stripped.split('：')[0][1:]}")
        fields.append(stripped)
    out_path.write_text("\n".join(fields) + "\n", encoding="utf-8")
    return out_path, warnings
def confirmation_issues(workdir: Path) -> list[str]:
    draft_dir = workdir / C.DRAFT_NAME
    issues: list[str] = []
    business_path = draft_dir / "业务理解.json"
    if not business_path.is_file() or not C.load_json(business_path).get("user_confirmed"):
        issues.append("业务理解尚未确认")
    elif not C.digest_current(C.load_json(business_path)):
        issues.append("业务理解在确认后被修改")
    selection_path = draft_dir / "代码文件选择.json"
    if not selection_path.is_file() or not C.load_json(selection_path).get("user_confirmed"):
        issues.append("代码文件选择尚未确认")
    elif not C.digest_current(C.load_json(selection_path)):
        issues.append("代码文件选择在确认后被修改")
    kind = C.manual_kind_of(draft_dir)
    shot_confirm = workdir / "截图方式确认.json"
    if kind == "operation":
        if not shot_confirm.is_file() or not C.load_json(shot_confirm).get("screenshot_method_confirmed"):
            issues.append("截图方式尚未确认")
        elif C.load_json(shot_confirm).get("screenshot_method") not in C.SHOT_METHODS:
            issues.append("截图方式取值无效")
        elif not C.digest_current(C.load_json(shot_confirm)):
            issues.append("截图方式确认在记录后被修改")
    elif shot_confirm.exists():
        issues.append("技术方案文档模式不应存在截图方式确认")
    app_md = draft_dir / "申请表信息.md"
    app_confirm = draft_dir / "申请表字段确认.json"
    if not app_confirm.is_file() or not C.load_json(app_confirm).get("application_fields_confirmed"):
        issues.append("申请表字段尚未确认")
    elif not app_md.is_file() or C.load_json(app_confirm).get("application_md_sha256") != C.sha256_file(app_md):
        issues.append("申请表信息在确认后被修改")
    final = draft_dir / "最终确认.json"
    if not final.is_file() or not C.load_json(final).get("markdown_confirmed"):
        issues.append("Markdown 草稿尚未最终确认")
    elif C.load_json(final).get("draft_file_sha256") != C.draft_snapshot(workdir):
        issues.append("草稿在最终确认后发生变化")
    issues.extend(C.draft_completeness_issues(workdir))
    return issues
def build_all(workdir: Path, software_name: str, version: str, skip_preview: bool, allow_untested: bool) -> dict[str, Any]:
    draft_dir = workdir / C.DRAFT_NAME
    final_dir = C.ensure_dir(workdir / C.FINAL_NAME)
    app_name = field_value(draft_dir / "申请表信息.md", "软件全称")
    app_version = field_value(draft_dir / "申请表信息.md", "版本号")
    final_name = app_name or software_name
    final_version = app_version or version
    safe = C.safe_name(final_name)
    warnings: list[str] = []
    if app_name and app_name != software_name:
        warnings.append(f"命令参数软件名 {software_name} 与申请表 {app_name} 不一致，已按申请表生成")
    if app_version and app_version != version:
        warnings.append(f"命令参数版本 {version} 与申请表 {app_version} 不一致，已按申请表生成")
    cli = OfficeCli(strict_version=not allow_untested)
    kind = C.manual_kind_of(draft_dir)
    shots: list[Path | None] = []
    if kind == "operation":
        method = (C.load_json(workdir / "截图方式确认.json") or {}).get("screenshot_method")
        if method == "skip":
            warnings.append("用户选择暂不截图；操作手册保留可见截图预留位置")
        elif method:
            manifest = workdir / "截图" / "截图清单.json"
            if not manifest.is_file():
                warnings.append("未找到截图清单；操作手册保留截图预留位置")
            elif (C.load_json(manifest).get("method") or "") != method:
                warnings.append("截图清单方式与确认方式不一致；保留预留位置")
            else:
                shots, shot_warnings = shot_paths(manifest, workdir)
                warnings.extend(shot_warnings)
    manifest = C.load_json(draft_dir / "代码提取清单.json")
    declared = [str(name) for name in manifest.get("outputs") or [] if str(name) in C.CODE_DRAFTS]
    for stale in (f"{safe}-代码(前30页).docx", f"{safe}-代码(后30页).docx", f"{safe}-代码(全部).docx"):
        (final_dir / stale).unlink(missing_ok=True)
    code_docx: Path | None = None
    estimated: int = 0
    for name in declared:
        code_docx = final_dir / f"{safe}-代码.docx"
        estimated = build_code_docx(cli, draft_dir / name, code_docx, final_name, final_version)
        break
    actual_pages: int | None = None
    if code_docx is not None:
        raw_pages = data_of(cli.stats(code_docx, page_count=True)).get("pages")
        if raw_pages is None:
            warnings.append("当前环境无法取得 Word 原生页数；提交前请在 Word/WPS 复核分页")
        else:
            actual_pages = int(raw_pages)
            if manifest.get("mode") == "front30_back30" and actual_pages != 60:
                raise OfficeCliError(f"{code_docx.name} Word 自动分页为 {actual_pages} 页，不是要求的前30页+后30页共 60 页；请重新校准选材量后生成。")
            if manifest.get("mode") != "front30_back30" and actual_pages != estimated:
                warnings.append(f"代码材料 Word 实际分页 {actual_pages} 页，与估算 {estimated} 页不同；申请表页数已按实际页数生成")
    app_txt, app_warnings = write_application_txt(draft_dir / "申请表信息.md", final_dir / "申请表信息.txt", actual_pages)
    warnings.extend(app_warnings)
    doc_md, _review_json, _review_md, suffix = C.PROSE_FILES[kind]
    other_suffix = C.PROSE_FILES["design" if kind == "operation" else "operation"][3]
    (final_dir / f"{safe}{other_suffix}").unlink(missing_ok=True)
    prose_docx: Path | None = None
    prose_md = draft_dir / doc_md
    if prose_md.is_file():
        prose_docx = final_dir / f"{safe}{suffix}"
        source = prose_md
        renamed: Path | None = None
        if app_name and app_name != software_name:
            renamed_text, leftover = rename_template_names(prose_md.read_text(encoding="utf-8"), software_name, app_name, kind, final_version)
            if leftover:
                warnings.append(f"文档草稿其余位置仍出现旧软件名“{software_name}”共 {leftover} 处；建议以申请表软件全称重新运行 manual_draft.py 并重新确认后生成")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", prefix=".softcopy-renamed-", dir=draft_dir, delete=False, encoding="utf-8") as handle:
                handle.write(renamed_text)
            renamed = Path(handle.name)
            source = renamed
        try:
            result = build_manual_docx(cli, source, prose_docx, draft_dir, final_name, final_version, shots if kind == "operation" else [])
            if kind == "operation":
                if result["inserted"]:
                    print(f"操作手册已插入截图 {result['inserted']} 张")
                if result["remaining_placeholders"]:
                    warnings.append(f"操作手册仍有 {result['remaining_placeholders']} 个截图预留位置未匹配图片")
                if result["unused_images"]:
                    warnings.append(f"截图清单有 {result['unused_images']} 张图片未匹配预留位置")
        finally:
            if renamed:
                renamed.unlink(missing_ok=True)
    else:
        warnings.append(f"缺少草稿/{doc_md}")
    prose_pages: int | None = None
    if prose_docx is not None:
        raw_prose_pages = data_of(cli.stats(prose_docx, page_count=True)).get("pages")
        if raw_prose_pages is not None:
            prose_pages = int(raw_prose_pages)
        prose_warning = prose_page_warning(prose_pages, prose_docx.name)
        if prose_warning:
            warnings.append(prose_warning)
    outputs = [app_txt] + [p for p in (code_docx, prose_docx) if p is not None]
    notes = verify_outputs(cli, outputs, code_docx, skip_preview, final_dir)
    if prose_docx is not None:
        notes.append(f"- `{prose_docx.name}`：Word 自动分页 {prose_pages if prose_pages is not None else '未能读取'} 页")
    report = write_report(final_dir, outputs, warnings, notes, cli.version)
    return {"outputs": [str(p) for p in outputs], "warnings": warnings, "report": str(report)}
def verify_outputs(cli: OfficeCli, outputs: list[Path], code_docx: Path | None, skip_preview: bool, final_dir: Path) -> list[str]:
    notes: list[str] = []
    preview_dir = final_dir / "预览"
    for output in outputs:
        if output.suffix.lower() != ".docx":
            continue
        verify_theme(cli, output)
        validation = cli.validate(output)
        errors = count_of(validation)
        if errors:
            raise OfficeCliError(f"{output.name} OpenXML 结构校验失败：{errors} 个错误")
        notes.append(f"- `{output.name}`：主题字体已统一为宋体/Times New Roman；OpenXML 结构错误 0；内容/格式提示 {count_of(cli.issues(output))} 个")
        if output == code_docx:
            stats = cli.stats(output, page_count=True)
            pages = data_of(stats).get("pages")
            notes.append(f"- `{output.name}`：Word 自动分页 {pages if pages is not None else '未能读取'} 页")
        if skip_preview:
            notes.append(f"- `{output.name}`：按参数跳过预览截图")
            continue
        preview = preview_dir / f"{output.stem}.png"
        try:
            cli.screenshot(output, preview)
            if preview.is_file():
                notes.append(f"- `{output.name}`：预览 {preview.relative_to(final_dir).as_posix()}")
        except (OfficeCliError, OSError) as exc:
            notes.append(f"- `{output.name}`：预览未生成（{exc}）")
    return notes
def write_report(final_dir: Path, outputs: list[Path], warnings: list[str], notes: list[str], officecli_version: str) -> Path:
    lines = ["# 生成报告", "", f"- DOCX 后端：OfficeCLI {officecli_version}", "- 自动更新：已禁用", "", "## 输出文件", ""]
    for path in outputs:
        size = path.stat().st_size if path.exists() else 0
        lines.append(f"- `{path.name}`（{size} 字节）")
    lines.extend(["", "## 警告", ""])
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- 无")
    lines.extend(["", "## 校验", ""])
    lines.extend(notes)
    report = final_dir / "生成报告.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default=C.ROOT_NAME)
    parser.add_argument("--software-name", required=True)
    parser.add_argument("--version", default="V1.0")
    parser.add_argument("--allow-untested-officecli", action="store_true",
                        help="OfficeCLI 版本不满足要求（低于下限或主版本变更）时，由用户明确承担风险继续正式生成")
    parser.add_argument("--skip-preview", action="store_true")
    args = parser.parse_args()
    workdir = Path(args.workdir)
    issues = confirmation_issues(workdir)
    if issues:
        C.stop_for_user("正式生成前必须完成以下确认：\n" + "\n".join(f"- {item}" for item in issues))
    try:
        result = build_all(workdir, args.software_name, args.version, args.skip_preview, args.allow_untested_officecli)
    except OfficeCliError as exc:
        raise SystemExit(f"DOCX_BUILD_FAILED\n{exc}")
    print(f"OK 申请资料：{workdir / C.FINAL_NAME}")
    for path in result["outputs"]:
        print(path)
    for warning in result["warnings"]:
        print(f"警告：{warning}")
    print(f"报告：{result['report']}")
if __name__ == "__main__":
    main()
