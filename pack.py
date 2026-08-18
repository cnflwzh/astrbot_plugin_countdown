"""Pack this plugin into a zip that AstrBot WebUI can install from file."""

from __future__ import annotations

import argparse
import fnmatch
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

SKIP_DIR_NAMES = {
    ".git",
    ".github",
    ".idea",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
}
SKIP_FILE_NAMES = {
    ".gitignore",
    ".gitattributes",
    ".DS_Store",
    "pack.py",
    "pytest.ini",
    "ruff.toml",
}
SKIP_GLOBS = (
    "*.pyc",
    "*.pyo",
    "*.json.tmp",
    "_tmp_*",
)


def read_metadata() -> dict[str, str]:
    meta: dict[str, str] = {}
    for raw in (ROOT / "metadata.yaml").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.startswith(" "):
            continue
        meta[key.strip()] = value.split("#", 1)[0].strip().strip("'\"")
    return meta


def should_skip(path: Path, *, include_tests: bool) -> bool:
    relative = path.relative_to(ROOT)
    parts = relative.parts
    if any(part in SKIP_DIR_NAMES for part in parts):
        return True
    if not include_tests and parts and parts[0] == "tests":
        return True
    if path.name in SKIP_FILE_NAMES:
        return True
    posix = relative.as_posix()
    return any(fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(posix, pattern) for pattern in SKIP_GLOBS)


def collect_files(*, include_tests: bool) -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path, include_tests=include_tests):
            continue
        files.append(path)
    files.sort()
    return files


def build_zip(destination: Path, files: list[Path], folder_name: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=Path(folder_name, path.relative_to(ROOT)).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 AstrBot 插件 zip，可直接在 WebUI 从文件安装")
    parser.add_argument("--include-tests", action="store_true", help="把 tests/ 一并打进包")
    parser.add_argument("-o", "--output", type=Path, help="输出 zip 路径，默认 dist/<name>-<version>.zip")
    args = parser.parse_args()

    meta = read_metadata()
    name = meta.get("name") or ROOT.name
    version = meta.get("version") or "v0.0.0"
    files = collect_files(include_tests=args.include_tests)
    if not files:
        raise SystemExit("没有可打包的文件")

    required = {"main.py", "metadata.yaml"}
    missing = required - {path.name for path in files if path.parent == ROOT}
    if missing:
        raise SystemExit(f"缺少必要文件：{', '.join(sorted(missing))}")

    destination = args.output or (DIST / f"{name}-{version}.zip")
    build_zip(destination, files, name)
    size_kb = destination.stat().st_size / 1024
    print(f"已生成 {destination}")
    print(f"体积 {size_kb:.1f} KB，{len(files)} 个文件")
    print("zip 根目录：")
    for path in files:
        print(f"  {name}/{path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
