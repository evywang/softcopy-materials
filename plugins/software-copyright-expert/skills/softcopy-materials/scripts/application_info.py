import argparse
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
import common as C
FIELD_ORDER = ["软件全称", "软件简称", "版本号", "软件分类", "开发完成日期", "开发方式", "软件说明", "发表状态", "首次发表日期", "著作权人", "权利范围", "权利取得方式", "开发的硬件环境", "运行的硬件环境", "开发该软件的操作系统", "软件开发环境 / 开发工具", "该软件的运行平台 / 操作系统", "软件运行支撑环境 / 支持软件", "编程语言", "源程序量", "开发目的", "面向领域 / 行业", "软件的主要功能", "软件的技术特点", "页数"]
ENUMS = {"软件分类": {"应用软件", "嵌入式软件", "中间件", "系统软件", "其他"}, "开发方式": {"单独开发", "合作开发", "委托开发", "下达任务开发"}, "软件说明": {"原创", "修改（含翻译软件、合成软件）"}, "发表状态": {"已发表", "未发表"}, "权利范围": {"全部权利", "部分权利"}, "权利取得方式": {"原始取得", "继受取得"}}
LIMITS = {"开发的硬件环境": 50, "运行的硬件环境": 50, "开发该软件的操作系统": 50, "软件开发环境 / 开发工具": 50, "该软件的运行平台 / 操作系统": 50, "软件运行支撑环境 / 支持软件": 50, "开发目的": 50, "面向领域 / 行业": 50, "软件的技术特点": 100, "编程语言": 120}
MAIN_MIN = 500
MAIN_MAX = 1300
def effective_len(value: str) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))
def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).replace("`", "").replace("#", "").strip()
def linux_os_release() -> str:
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip('"\'')[:40]
    except OSError:
        pass
    return ""
def os_label() -> str:
    system = platform.system()
    if system == "Darwin":
        version = platform.mac_ver()[0]
        return f"macOS {version}" if version else "macOS"
    if system == "Windows":
        release = platform.release()
        return f"Windows {release}" if release else "Windows"
    if system == "Linux":
        return linux_os_release() or f"Linux {platform.release()}"
    return f"{system} {platform.release()}".strip() or "待确认"
CPU_BRAND_LABELS = {"GenuineIntel": "Intel", "AuthenticAMD": "AMD", "GenuineIntel(x86)": "Intel", "CentaurHauls": "VIA", "ARM": "ARM"}
def trim_brand_words(brand: str, limit: int = 26) -> str:
    words: list[str] = []
    total = 0
    for word in brand.split():
        step = len(word) + (1 if words else 0)
        if total + step > limit:
            break
        words.append(word)
        total += step
    while words and (len(words[-1]) < 3 or "/" in words[-1]):
        words.pop()
    if not words and brand:
        return brand[:limit]
    return " ".join(words)
def posix_cpu_brand() -> str:
    if sys.platform == "darwin":
        try:
            done = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=10, check=False)
            if done.returncode == 0 and done.stdout.strip():
                return trim_brand_words(done.stdout.strip().splitlines()[0])
        except (OSError, subprocess.SubprocessError):
            pass
        return ""
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("model name"):
                brand = line.split(":", 1)[1].strip()
                if brand.upper().endswith(" PROCESSOR"):
                    brand = brand[: -len(" PROCESSOR")].rstrip()
                return trim_brand_words(brand)
    except OSError:
        pass
    return ""
def cpu_brand() -> str:
    if os.name == "nt":
        tokens = os.environ.get("PROCESSOR_IDENTIFIER", "").replace(",", " ").split()
        return CPU_BRAND_LABELS.get(tokens[-1], "") if tokens else ""
    return posix_cpu_brand()
def hardware_hint() -> str:
    parts: list[str] = []
    brand = cpu_brand()
    cores = os.cpu_count() or 0
    cpu = f"{brand}处理器" if brand else "通用处理器"
    if cores:
        cpu += f"{cores}核"
    parts.append(cpu)
    mem = C.memory_gb()
    if mem:
        parts.append(f"内存{mem}GB")
    disk = C.disk_gb()
    if disk:
        parts.append(f"硬盘{disk}GB")
    text = "、".join(parts)
    return text[:LIMITS["开发的硬件环境"]] if text else "待确认"
def ide_hint(root: Path) -> str:
    if (root / ".idea").exists():
        return "IntelliJ IDEA 或 WebStorm"
    return "Visual Studio Code"
def support_hint(analysis: dict[str, Any], root: Path) -> str:
    items: list[str] = []
    deps = set((analysis.get("package") or {}).get("dependency_names") or [])
    if analysis.get("package") or deps:
        items.append("Node.js")
        items.append("npm")
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists() or list(root.glob("*/requirements*.txt")):
        items.append("Python")
    if (root / "docker-compose.yml").exists() or (root / "docker-compose.yaml").exists():
        items.extend(["Docker", "Docker Compose"])
    if any(dep.lower().startswith("pg") or "postgres" in dep.lower() for dep in deps):
        items.append("PostgreSQL")
    if any("redis" in dep.lower() for dep in deps):
        items.append("Redis")
    if not items:
        items.append("现代浏览器")
    text = "、".join(dict.fromkeys(items))
    return text[:LIMITS["软件运行支撑环境 / 支持软件"]] if text else "待确认"
def version_hint(analysis: dict[str, Any], requested: str) -> str:
    project_version = str((analysis.get("package") or {}).get("version") or "").strip()
    parts = [int(p) for p in re.findall(r"\d+", requested)][:3] or [1]
    looks_below_v1 = bool(parts) and parts[0] < 1
    if project_version and project_version.upper() != "V1.0":
        return f"待确认（项目版本 {project_version}，当前建议 {requested}；请确认最终申报版本号）"
    if looks_below_v1:
        return f"待确认（当前建议 {requested} 低于 V1.0，软著首次提交通常建议 V1.0；请确认最终版本号）"
    return f"待确认（建议 {requested}；请确认最终版本号）"
def build_fields(analysis: dict[str, Any], manifest: dict[str, Any], software_name: str, version: str, answers: dict[str, str], business: dict[str, Any]) -> dict[str, str]:
    project = Path(analysis.get("project_root") or ".")
    fields = {
        "软件全称": f"待确认（建议：{software_name}；请确认最终软件全称）",
        "软件简称": "",
        "版本号": version_hint(analysis, version),
        "软件分类": str(business.get("software_category") or "应用软件"),
        "开发完成日期": "待确认（YYYY-MM-DD）",
        "开发方式": "待确认（单独开发/合作开发/委托开发/下达任务开发）",
        "软件说明": "原创",
        "发表状态": "待确认（已发表/未发表）",
        "首次发表日期": "待确认（YYYY-MM-DD，未发表则留空）",
        "著作权人": "待确认",
        "权利范围": "待确认（全部权利/部分权利）",
        "权利取得方式": "待确认（原始取得/继受取得）",
        "开发的硬件环境": hardware_hint(),
        "运行的硬件环境": hardware_hint(),
        "开发该软件的操作系统": os_label(),
        "软件开发环境 / 开发工具": f"开发环境: {os_label()}/开发工具: {ide_hint(project)}"[:LIMITS["软件开发环境 / 开发工具"]],
        "该软件的运行平台 / 操作系统": os_label(),
        "软件运行支撑环境 / 支持软件": support_hint(analysis, project),
        "编程语言": str(analysis.get("language") or "待确认"),
        "源程序量": str((analysis.get("source") or {}).get("line_count") or "待确认"),
        "开发目的": str(business.get("application_purpose") or "待确认（不超过50字，不能只写软件名称）"),
        "面向领域 / 行业": str(business.get("industry") or "待确认"),
        "软件的主要功能": str(business.get("main_functions") or ""),
        "软件的技术特点": str(business.get("technical_characteristics") or "待确认（不超过100字）"),
        "页数": str(manifest.get("submitted_pages") or "待确认"),
    }
    for key, value in answers.items():
        if key in fields and str(value).strip():
            fields[key] = str(value).strip()
    publish = fields.get("发表状态", "")
    if "未发表" in publish and "已发表" not in publish:
        if "待确认" in fields.get("首次发表日期", "") or not fields.get("首次发表日期", "").strip():
            fields["首次发表日期"] = ""
    return fields
def valid_date(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        __import__("datetime").datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False
def field_issues(fields: dict[str, str]) -> list[str]:
    issues: list[str] = []
    for field in FIELD_ORDER:
        if field == "软件简称" or field == "首次发表日期":
            continue
        value = fields.get(field, "")
        if not value.strip() or "待确认" in value:
            issues.append(f"➤{field}：待确认")
            continue
        limit = LIMITS.get(field)
        if limit and effective_len(value) > limit:
            issues.append(f"➤{field}：{effective_len(value)} 字，超过 {limit} 字上限")
        allowed = ENUMS.get(field)
        if allowed and value not in allowed:
            issues.append(f"➤{field}：值“{value}”不在允许范围内（{'/'.join(sorted(allowed))}）")
    for field in ("开发完成日期", "首次发表日期"):
        value = fields.get(field, "")
        if value and "待确认" not in value and not valid_date(value):
            issues.append(f"➤{field}：必须为有效的 YYYY-MM-DD 日期")
    if fields.get("发表状态") == "已发表" and not fields.get("首次发表日期", "").strip():
        issues.append("➤首次发表日期：发表状态为已发表时必填")
    for field in ("源程序量", "页数"):
        value = fields.get(field, "")
        if value and "待确认" not in value and not value.isdigit():
            issues.append(f"➤{field}：必须为纯数字")
    main = fields.get("软件的主要功能", "")
    if main and "待确认" not in main:
        length = effective_len(main)
        if length < MAIN_MIN or length > MAIN_MAX:
            issues.append(f"➤软件的主要功能：{length} 字，需在 {MAIN_MIN}~{MAIN_MAX} 字之间")
    return issues
def write_md(path: Path, fields: dict[str, str], analysis: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    issues = field_issues(fields)
    lines = ["# 申请表信息", ""]
    for field in FIELD_ORDER:
        lines.append(f"➤{field}：{fields.get(field, '待确认')}")
    lines.extend([
        "",
        "## 字段口径",
        "",
        "- 软件全称与版本号以本文件为准，正式文件名、页眉、标题与正文统一使用。",
        "- 软件全称建议以「软件」「平台」「系统」结尾。",
        "- 版本号：项目版本低于 V1.0 时，软著首次提交通常建议填写 V1.0，以用户确认为准。",
        "- 日期字段一律 YYYY-MM-DD。",
        "- 源程序量为登记软件全部源程序总行数（含空行），不是抽取材料的行数。",
        "- 页数为实际提交的代码鉴别材料页数；前30页+后30页模式填 60，不足时填全部材料页数。",
        "- 软件开发环境 / 开发工具填 IDE，不填 React、Vite、TypeScript 等技术栈。",
        "- 开发的硬件环境、运行的硬件环境等字段上限 50 字。",
        "- 软件的主要功能 500~1300 字；技术特点描述不超过 100 字。",
        "",
        "## 项目摘要",
        "",
        f"- 项目目录：{analysis.get('project_root', '')}",
        f"- 框架：{'、'.join(analysis.get('frameworks') or []) or '未识别'}",
        f"- 源码文件数：{(analysis.get('source') or {}).get('file_count', 0)}",
        f"- 源程序量（含空行）：{(analysis.get('source') or {}).get('line_count', 0)}",
        f"- 代码输出模式：{manifest.get('mode', '')}",
        f"- 提交材料页数（估算）：{manifest.get('submitted_pages', '')}",
        "",
    ])
    pending = [issue for issue in issues if issue.endswith("：待确认")]
    lines.append("## 待确认字段")
    lines.append("")
    lines.extend(f"- {issue[1:].split('：')[0]}" for issue in pending)
    if not pending:
        lines.append("- 无")
    lines.append("")
    others = [issue for issue in issues if not issue.endswith("：待确认")]
    if others:
        lines.append("## 字段提醒")
        lines.append("")
        lines.extend(f"- {issue[1:]}" for issue in others)
        lines.append("")
    lines.extend(["```text", "STOP_FOR_USER", "NEXT_ACTION: 请补全并确认申请表字段；确认后运行 confirm_gate.py --stage application-fields。", "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return issues
def require_business(business: dict[str, Any] | None) -> None:
    if business is None:
        C.stop_for_user("申请表必须基于已确认的业务理解生成；请先完成业务理解并记录 business 门禁。")
    if business.get("confirmation_required") and not business.get("user_confirmed"):
        C.stop_for_user("业务理解尚未确认；请先记录 business 门禁。")
    if business.get("user_confirmed") and not C.digest_current(business):
        C.stop_for_user("业务理解在确认后被修改；请重新核对并重新记录 business 门禁。")
    main = str(business.get("main_functions") or "")
    if not MAIN_MIN <= effective_len(main) <= MAIN_MAX:
        C.stop_for_user("业务理解中的主要功能字数不满足 500~1300 字；请回到业务理解阶段补写，本脚本不做填充式兜底。")
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--code-manifest", required=True)
    parser.add_argument("--business-context", required=True)
    parser.add_argument("--software-name", required=True)
    parser.add_argument("--version", default="V1.0")
    parser.add_argument("--answers", default="")
    parser.add_argument("--out-dir", default=f"{C.ROOT_NAME}/{C.DRAFT_NAME}")
    args = parser.parse_args()
    analysis = C.load_json(Path(args.analysis))
    manifest = C.load_json(Path(args.code_manifest))
    business = C.load_json(Path(args.business_context))
    require_business(business)
    answers = C.load_json(Path(args.answers)) if args.answers else {}
    fields = build_fields(analysis, manifest, args.software_name, args.version, answers if isinstance(answers, dict) else {}, business)
    out = Path(args.out_dir) / "申请表信息.md"
    issues = write_md(out, fields, analysis, manifest)
    print(f"OK 申请表草稿：{out}")
    print(f"待处理字段问题：{len(issues)}")
    C.stop_for_user("请补全并确认申请表字段；确认后运行 confirm_gate.py --stage application-fields。")
if __name__ == "__main__":
    main()
