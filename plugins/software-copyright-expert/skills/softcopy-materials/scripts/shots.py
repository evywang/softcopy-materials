import argparse
import re
import shutil
from pathlib import Path
from typing import Any
import common as C
ALLOWED = {".png", ".jpg", ".jpeg", ".webp"}
def sort_key(path: Path) -> tuple[int, int, str]:
    match = re.match(r"^(\d+)", path.stem)
    if match:
        return (0, int(match.group(1)), path.name.casefold())
    return (1, 0, path.name.casefold())
def safe_stem(stem: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", stem).strip()
    return cleaned[:60] or "page"
def organize(input_dir: Path, out_dir: Path, method: str) -> dict[str, Any]:
    if input_dir.resolve() == out_dir.resolve():
        raise SystemExit("截图输入与输出目录不能相同")
    if not input_dir.is_dir():
        raise SystemExit(f"截图目录不存在：{input_dir}")
    C.ensure_dir(out_dir)
    images = sorted((p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED), key=sort_key)
    screenshots: list[dict[str, str]] = []
    for index, path in enumerate(images, start=1):
        target = out_dir / f"{index:02d}-{safe_stem(path.stem)}{path.suffix.lower()}"
        if path.resolve() != target.resolve():
            shutil.copy2(path, target)
        screenshots.append({"path": str(target.resolve()), "source": str(path.resolve())})
    manifest: dict[str, Any] = {"status": "ok" if screenshots else "empty", "method": method, "screenshots": screenshots}
    C.save_json(out_dir / "截图清单.json", manifest)
    return manifest
def main() -> None:
    C.ensure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--out-dir", default=f"{C.ROOT_NAME}/截图")
    parser.add_argument("--method", required=True, choices=["agent-browser", "playwright-cli", "user-supplied"])
    args = parser.parse_args()
    manifest = organize(Path(args.input_dir), Path(args.out_dir), args.method)
    print(f"OK 截图清单：{Path(args.out_dir) / '截图清单.json'}")
    print(f"图片数量：{len(manifest['screenshots'])}")
    if not manifest["screenshots"]:
        raise SystemExit(3)
if __name__ == "__main__":
    main()
