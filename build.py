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
APP_NAME = "DesktopPet"


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
        "--name", APP_NAME,
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
        # macOS: 生成单文件 .app（不含多余文件夹）
        cmd.append("--onedir")  # 保留 .app bundle 结构

    # 自动发现资源
    cmd.extend(collect_add_data())

    # 主入口
    cmd.append(str(ROOT / "main.py"))

    print(f"[BUILD] 目标平台: {target}")
    print(f"[BUILD] 命令: {' '.join(cmd)}")
    print("-" * 60)

    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode


def make_dmg():
    """
    macOS: 创建标准 DMG 安装盘。
    用户打开 DMG 后拖拽 .app 到 Applications 文件夹即可安装。
    """
    app_path = ROOT / "dist" / f"{APP_NAME}.app"
    if not app_path.exists():
        print("[DMG] 找不到 .app，请先执行打包")
        return 1

    dmg_path = ROOT / "dist" / f"{APP_NAME}.dmg"
    staging = ROOT / "dist" / "dmg_staging"

    # 准备临时目录
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()

    # 拷贝 .app 到临时目录
    shutil.copytree(app_path, staging / f"{APP_NAME}.app")

    # 创建指向 /Applications 的快捷方式
    subprocess.run(
        ["ln", "-s", "/Applications", str(staging / "Applications")],
        check=True,
    )

    # 删除旧 DMG
    if dmg_path.exists():
        dmg_path.unlink()

    print(f"[DMG] 正在生成 {dmg_path.name} ...")
    subprocess.run(
        [
            "hdiutil", "create",
            "-volname", APP_NAME,
            "-srcfolder", str(staging),
            "-ov", "-format", "UDZO",
            str(dmg_path),
        ],
        check=True,
    )

    # 清理临时目录
    shutil.rmtree(staging)

    size = dmg_path.stat().st_size
    print(f"[DMG] ✅ 已生成 {dmg_path} ({size / 1024 / 1024:.1f} MB)")
    return 0


def main():
    parser = argparse.ArgumentParser(description="打包桌面宠物")
    parser.add_argument(
        "--target",
        choices=("windows", "mac", "auto"),
        default="auto",
        help="目标平台 (默认: auto = 当前系统)",
    )
    parser.add_argument(
        "--dmg",
        action="store_true",
        help="(仅 macOS) 同时生成 DMG 安装盘",
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

    if ret != 0:
        print(f"\n❌ 打包失败 (exit code: {ret})")
        return ret

    print(f"\n✅ 打包完成！")

    # 生成 DMG
    if args.dmg and target == "mac":
        dmg_ret = make_dmg()
        if dmg_ret != 0:
            return dmg_ret
    elif args.dmg and target != "mac":
        print("[WARN] --dmg 仅在 macOS 目标下有效，已跳过")

    dist = ROOT / "dist"
    if dist.exists():
        print(f"\n产物列表 ({dist}):")
        for item in sorted(dist.iterdir()):
            print(f"   {item.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
