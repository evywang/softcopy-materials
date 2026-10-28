#!/usr/bin/env python3
"""把专家市场目录打包成可分发的市场 zip。

WorkBuddy 的市场清单查找规则（来自 CLI 的 listManifestPaths）：
    <root>/marketplace.json
    <root>/.codebuddy-plugin/marketplace.json
    <root>/.workbuddy-plugin/marketplace.json
    <root>/.claude-plugin/marketplace.json

因此清单必须位于**压缩包根目录**，不能在多套一层文件夹里；
清单声明的本地插件路径（source: "./plugins/<name>"）也必须随包分发。

注意：本地目录型市场（~/.workbuddy/plugins/marketplaces/<name>/）由 WorkBuddy 托管，
它会把 marketplace.json 规范化成最小结构（只保留 name/description 与
插件的 name/source/description），owner、version、description_zh 等字段会被清掉。
而 zip 安装型市场是只读的，保留完整元数据。
所以**富元数据的权威副本要放在本脚本的 --marketplace-dir 里**（通常是你的源码仓库），
本地托管目录只负责让专家在本机可见。

用法：
    python scripts/build_marketplace.py \
        --marketplace-dir <市场源目录> \
        --expert-dir <专家目录> [--expert-dir <专家目录> ...] \
        --out <输出zip>
"""

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

MANIFEST_DIRS = (".codebuddy-plugin", ".workbuddy-plugin", ".claude-plugin")
MANIFEST_NAME = "marketplace.json"
SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".idea", ".vscode", "dist", "build"}
SKIP_FILES = {".DS_Store", "Thumbs.db", ".gitkeep"}
SKIP_SUFFIX = (".pyc", ".pyo", ".map", ".log")


def find_manifest(market_dir: Path) -> Path | None:
    direct = market_dir / MANIFEST_NAME
    if direct.is_file():
        return direct
    for name in MANIFEST_DIRS:
        candidate = market_dir / name / MANIFEST_NAME
        if candidate.is_file():
            return candidate
    return None


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name in SKIP_FILES or path.name.startswith("."):
            continue
        if path.suffix.lower() in SKIP_SUFFIX:
            continue
        files.append(path)
    return files


def verify(manifest: dict, files: list[Path], market_dir: Path) -> list[str]:
    """打包前自检：清单声明的本地插件必须真的在包内。"""
    issues: list[str] = []
    shipped = {path.relative_to(market_dir).as_posix() for path in files}
    for plugin in manifest.get("plugins") or []:
        if not isinstance(plugin, dict):
            continue
        source = str(plugin.get("source") or "")
        if not source.startswith("./"):
            continue
        relative = source[2:].rstrip("/")
        prefix = f"{relative}/"
        if not any(item == relative or item.startswith(prefix) for item in shipped):
            issues.append(
                f"清单声明的插件「{plugin.get('name')}」({source}) 不在打包范围内，"
                "安装方会拿到一个缺插件的市场"
            )
    return issues


def stage(market_dir: Path, expert_dirs: list[Path]) -> Path:
    """把市场源目录与各专家目录合成一个暂存目录。

    市场源目录保留富元数据（owner/version/description_zh 等）；
    专家目录按插件名放进 plugins/ 下。
    """
    staging = Path(tempfile.mkdtemp(prefix="softcopy-mkt-build-"))
    target_market = staging / market_dir.name
    shutil.copytree(market_dir, target_market, ignore=shutil.ignore_patterns(
        "__pycache__", "node_modules", "*.pyc", ".git"))
    plugins_dir = target_market / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    for expert_dir in expert_dirs:
        if not expert_dir.is_dir():
            raise SystemExit(f"专家目录不存在：{expert_dir}")
        plugin_json = None
        for name in MANIFEST_DIRS:
            candidate = expert_dir / name / "plugin.json"
            if candidate.is_file():
                plugin_json = candidate
                break
        if plugin_json is None:
            raise SystemExit(f"专家目录缺少 plugin.json：{expert_dir}")
        plugin_name = json.loads(plugin_json.read_text(encoding="utf-8")).get("name") or expert_dir.name
        dest = plugins_dir / plugin_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(expert_dir, dest, ignore=shutil.ignore_patterns(
            "__pycache__", "node_modules", "*.pyc", ".git"))
    return staging


def build(market_dir: Path, out_path: Path, expert_dirs: list[Path] | None = None) -> tuple[int, list[str]]:
    manifest_path = find_manifest(market_dir)
    if manifest_path is None:
        raise SystemExit(
            f"在 {market_dir} 下找不到市场清单："
            f"需要 {MANIFEST_NAME} 或 {' / '.join(d + '/' + MANIFEST_NAME for d in MANIFEST_DIRS)}"
        )
    staging = None
    try:
        if expert_dirs:
            staging = stage(market_dir, expert_dirs)
            source_root = staging / market_dir.name
        else:
            source_root = market_dir
        manifest = json.loads(find_manifest(source_root).read_text(encoding="utf-8"))
        files = collect_files(source_root)
        issues = verify(manifest, files, source_root)
        if issues:
            raise SystemExit("打包前自检未通过：\n" + "\n".join(f"- {item}" for item in issues))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            out_path.unlink()
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                # 清单必须在压缩包根：统一以相对市场根的路径写入
                archive.write(path, path.relative_to(source_root).as_posix())
        return len(files), issues
    finally:
        if staging:
            shutil.rmtree(staging, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marketplace-dir", required=True,
                        help="市场源目录（含 .codebuddy-plugin/marketplace.json，富元数据的权威副本放这里）")
    parser.add_argument("--expert-dir", action="append", default=[],
                        help="要打进市场包的专家目录，可重复指定")
    parser.add_argument("--out", required=True, help="输出 zip 路径")
    args = parser.parse_args()
    market_dir = Path(args.marketplace_dir).expanduser().resolve()
    if not market_dir.is_dir():
        raise SystemExit(f"市场目录不存在：{market_dir}")
    expert_dirs = [Path(item).expanduser().resolve() for item in args.expert_dir]
    count, _ = build(market_dir, Path(args.out).expanduser().resolve(), expert_dirs)
    print(f"OK 市场分发包：{args.out}")
    print(f"文件数：{count}")
    print("分发方式：")
    print("  1. 把 zip 上传到任意可访问的 HTTP 地址，然后让使用方执行 /plugin marketplace add <该地址>")
    print("  2. 或把市场源目录放进 Git 仓库，让使用方执行 /plugin marketplace add <owner>/<repo>")
    print("  3. 使用方再执行 /plugin install <插件名>@<市场名>")


if __name__ == "__main__":
    main()
