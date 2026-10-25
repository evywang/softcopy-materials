import argparse
import re
from collections import Counter
from pathlib import Path
from typing import Any
import common as C
FRAMEWORK_DEPS = {"vue": "Vue", "@vue/runtime-core": "Vue", "react": "React", "next": "Next.js", "nuxt": "Nuxt", "svelte": "Svelte", "astro": "Astro", "@angular/core": "Angular", "vite": "Vite", "uni-app": "UniApp", "@dcloudio/uni-app": "UniApp", "electron": "Electron", "@tauri-apps/api": "Tauri", "express": "Express", "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "spring-boot": "Spring Boot", "gin-gonic/gin": "Gin"}
LANG_BY_EXT = {".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".py": "Python", ".java": "Java", ".go": "Go", ".rs": "Rust", ".cs": "C#", ".php": "PHP", ".rb": "Ruby", ".kt": "Kotlin", ".swift": "Swift", ".c": "C", ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".h": "C/C++", ".hh": "C++", ".hpp": "C++", ".dart": "Dart", ".gd": "GDScript", ".gml": "GameMaker Language", ".lua": "Lua", ".sql": "SQL", ".sh": "Shell", ".vue": "Vue", ".svelte": "Svelte", ".astro": "Astro", ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang", ".clj": "Clojure", ".scala": "Scala", ".zig": "Zig", ".nim": "Nim", ".jl": "Julia", ".r": "R", ".v": "Verilog", ".sv": "SystemVerilog", ".m": "Objective-C", ".mm": "Objective-C++"}
CATEGORY_NAMES = {0: "entry", 10: "route", 20: "page", 30: "api", 40: "state", 45: "model", 50: "component", 60: "utility", 70: "server", 80: "frontend", 85: "source", 90: "style"}
STOP_WORDS = {"index", "main", "app", "layout", "page", "globals", "providers", "loading", "error", "not-found", "template", "default", "button", "input", "label", "avatar", "card", "textarea", "utils", "helpers", "types", "constants", "config", "readme"}
def load_package(root: Path) -> tuple[dict[str, Any] | None, Path | None]:
    for candidate in (root / "package.json", root / "frontend" / "package.json", root / "client" / "package.json", root / "web" / "package.json", root / "app" / "package.json"):
        if not candidate.exists():
            continue
        try:
            return C.load_json(candidate), candidate
        except Exception:
            continue
    return None, None
CONFIG_FRAMEWORK_LABELS = {"vite.config.ts": "Vite", "vite.config.js": "Vite", "next.config.js": "Next.js", "next.config.ts": "Next.js", "next.config.mjs": "Next.js", "nuxt.config.ts": "Nuxt", "nuxt.config.js": "Nuxt", "angular.json": "Angular"}
def detect_frameworks(package: dict[str, Any] | None, files: list[Path], root: Path) -> list[str]:
    found: set[str] = set()
    if package:
        deps: dict[str, Any] = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            deps.update(package.get(key) or {})
        for dep in deps:
            if dep in FRAMEWORK_DEPS:
                found.add(FRAMEWORK_DEPS[dep])
    suffixes = {p.suffix.lower() for p in files}
    if ".vue" in suffixes:
        found.add("Vue")
    if (".tsx" in suffixes or ".jsx" in suffixes) and "Vue" not in found:
        found.add("React")
    for name, label in CONFIG_FRAMEWORK_LABELS.items():
        if (root / name).exists():
            found.add(label)
    return sorted(found)
def infer_language(ext_counts: Counter[str]) -> str:
    langs: list[str] = []
    for ext, label in LANG_BY_EXT.items():
        if ext_counts.get(ext):
            langs.append(label)
    known = set(LANG_BY_EXT)
    for ext, _count in ext_counts.most_common():
        if ext and ext not in known and len(langs) < 5:
            langs.append(f"{ext.lstrip('.')} 源码")
        if len(langs) >= 5:
            break
    return "、".join(dict.fromkeys(langs)) or "待确认"
def extract_routes(path: Path) -> list[str]:
    try:
        text = C.read_text(path, limit=200000)
    except Exception:
        return []
    routes: list[str] = []
    for pattern in (r"path\s*:\s*['\"]([^'\"]+)['\"]", r"<Route[^>]+path=['\"]([^'\"]+)['\"]", r"href=['\"](/[^'\"]*)['\"]"):
        for hit in re.findall(pattern, text):
            if hit.startswith("/") and len(hit) < 120 and "*" not in hit and hit not in routes:
                routes.append(hit)
    return routes
def readme_excerpt(root: Path) -> str:
    for name in ("README.md", "README.zh.md", "readme.md", "Readme.md", "README.txt"):
        path = root / name
        if path.exists():
            text = C.read_text(path, limit=6000)
            return "\n".join(line.strip() for line in text.splitlines()[:60] if line.strip())
    return ""
def feature_names(files: list[Path], root: Path) -> list[str]:
    names: list[str] = []
    for path in files:
        if C.category_weight(path, root) != 20:
            continue
        parts = [p for p in Path(C.rel_posix(path, root)).parts]
        stems = [Path(p).stem for p in parts if Path(p).stem.lower() not in {"index", "page", "layout", "route", "loading", "error"} and not p.startswith("[") and not p.startswith("(")]
        if stems:
            name = " ".join(stems[-2:]).replace("-", " ").replace("_", " ").strip()
            if name and name.lower() not in STOP_WORDS and name not in names:
                names.append(name)
    return names[:30]
def env_gate(root_out: Path) -> None:
    env_path = root_out / "环境探测.json"
    if not env_path.exists():
        return
    try:
        env = C.load_json(env_path)
    except Exception:
        return
    if not env.get("requires_user_input"):
        return
    confirmed = C.load_json(root_out / "环境确认.json") if (root_out / "环境确认.json").exists() else {}
    if confirmed.get("environment_confirmed") and C.digest_current(confirmed):
        return
    C.stop_for_user("OfficeCLI 环境尚未就绪或未确认。请按环境探测提示处理并记录 environment 门禁后再继续。")
def analyze(root: Path) -> dict[str, Any]:
    root = root.resolve()
    package, package_path = load_package(root)
    sources = list(C.iter_sources(root))
    ext_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    categorized: dict[str, list[str]] = {}
    total_lines = 0
    routes = ["/"]
    for path in sources:
        rel = C.rel_posix(path, root)
        ext = path.suffix.lower()
        ext_counts[ext] += 1
        weight = C.category_weight(path, root)
        name = CATEGORY_NAMES.get(weight, "source")
        category_counts[name] += 1
        categorized.setdefault(name, []).append(rel)
        total_lines += len(C.read_text(path).splitlines())
        if weight in (0, 10, 20) and ext in {".ts", ".tsx", ".js", ".jsx", ".vue"}:
            routes.extend(extract_routes(path))
    frameworks = detect_frameworks(package, sources, root)
    package_info: dict[str, Any] = {}
    if package:
        package_info = {"name": str(package.get("name") or ""), "version": str(package.get("version") or ""), "path": C.rel_posix(package_path, root) if package_path else "", "scripts": {k: str(v) for k, v in (package.get("scripts") or {}).items()}, "dependency_names": sorted({k for key in ("dependencies", "devDependencies") for k in (package.get(key) or {})})}
    run_commands = [f"npm run {key}" for key in ("dev", "start", "serve", "preview") if package and key in (package.get("scripts") or {})]
    return {
        "project_root": str(root),
        "project_name": root.name,
        "software_name_candidate": re.sub(r"[\s\-_]+", "", str((package_info.get("name") if package_info else "") or root.name)) or root.name,
        "frameworks": frameworks,
        "language": infer_language(ext_counts),
        "source": {"file_count": len(sources), "line_count": total_lines, "extension_counts": dict(sorted(ext_counts.items())), "category_counts": dict(sorted(category_counts.items())), "categorized_files": {k: v[:80] for k, v in sorted(categorized.items()) if v}},
        "routes": sorted(set(routes), key=lambda x: (x.count("/"), x))[:80],
        "readme_excerpt": readme_excerpt(root),
        "run_command_candidates": run_commands,
        "feature_name_candidates": feature_names(sources, root),
        "package": package_info,
    }
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", default=f"{C.ROOT_NAME}/analysis/project.json")
    args = parser.parse_args()
    project = Path(args.project)
    if not project.exists():
        raise SystemExit(f"项目目录不存在：{project}")
    out = Path(args.out)
    env_gate(out.parent.parent if out.parent.name == "analysis" else out.parent)
    data = analyze(project)
    C.save_json(out, data)
    print(f"OK 项目分析：{out}")
    print(f"框架：{'、'.join(data['frameworks']) or '未识别'}")
    print(f"语言：{data['language']}")
    print(f"源码文件：{data['source']['file_count']}")
    print(f"源程序总行数：{data['source']['line_count']}")
if __name__ == "__main__":
    main()
