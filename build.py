#!/usr/bin/env python3
"""桌面宠物打包脚本 — 自动发现所有 GIF 资源，支持 Windows / macOS 双平台。"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ACTIONS_DIR = ROOT / "actions"


def collect_add_data():
    """
    自动扫描 actions/ 目录，为每个子目录生成 --add-data 参数。
    PyInstaller 的格式: --add-data "源路径:目标路径"
      - Windows 用 ; 分隔
      - macOS/Linux 用 : 分隔
    """
    sep = ";" if sys.platform == "win32" else ":"
    args = []

    # 整个 actions/ 目录打包进去，PyInstaller 会保留内部结构
    args.extend(["--add-data", f"actions{sep}actions"])

    # 图标文件
    for ext in (".png", ".ico", ".icns"):
        icon_file = ROOT / f"icon{ext}"
        if icon_file.exists():
            args.extend(["--add-data", f"icon{ext}{sep}."])

    return args


def clean():
    """清理上次构建产物。"""
    for d in ("build", "dist"):
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)
            print(f"[CLEAN] 已删除 {d}/")


def build(target: str) -> int:
    """执行 PyInstaller 打包。"""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--windowed",
        "--name", "DesktopPet",
        "--clean",
    ]

    # --- 平台图标 ---
    if target == "windows":
        icon = ROOT / "icon.ico"
        if icon.exists():
            cmd.extend(["--icon", str(icon)])
    elif target == "mac":
        icon = ROOT / "icon.icns"
        if icon.exists():
            cmd.extend(["--icon", str(icon)])

    # 自动发现资源
    cmd.extend(collect_add_data())

    # 主入口
    cmd.append(str(ROOT / "main.py"))

    print(f"[BUILD] 目标平台: {target}")
    print(f"[BUILD] 命令: {' '.join(cmd)}")
    print("-" * 60)

    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="打包桌面宠物")
    parser.add_argument(
        "--target",
        choices=("windows", "mac", "auto"),
        default="auto",
        help="目标平台 (默认: auto = 当前系统)",
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="仅清理构建产物",
    )
    args = parser.parse_args()

    if args.target == "auto":
        if sys.platform == "win32":
            target = "windows"
        elif sys.platform == "darwin":
            target = "mac"
        else:
            print("[ERROR] 不支持的平台，请用 --target windows 或 --target mac")
            return 1
    else:
        target = args.target

    if args.clean_only:
        clean()
        return 0

    clean()
    ret = build(target)

    if ret == 0:
        print("\n✅ 打包完成！产物在 dist/ 目录")
        dist = ROOT / "dist"
        if dist.exists():
            for item in sorted(dist.iterdir()):
                print(f"   {item.name}")
    else:
        print(f"\n❌ 打包失败 (exit code: {ret})")

    return ret


if __name__ == "__main__":
    sys.exit(main())
