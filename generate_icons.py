#!/usr/bin/env python3
"""从 SVG 或 PNG 高清原图生成 macOS / Windows 所需的全部图标格式。

用法:
    python3 generate_icons.py icon.svg
    python3 generate_icons.py icon_1024.png

SVG 为最佳选择 — 矢量无损，生成任意尺寸均清晰锐利。
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ICONSET_SIZES = [16, 32, 64, 128, 256, 512, 1024]
ROOT = Path(__file__).resolve().parent


def svg_to_png(svg_path: Path, size: int, output: Path):
    """用 macOS 内置的 qlmanage 将 SVG 渲染为指定尺寸的 PNG。"""
    tmp_dir = Path(tempfile.mkdtemp())
    subprocess.run(
        ["qlmanage", "-t", "-s", str(size), "-o", str(tmp_dir), str(svg_path)],
        capture_output=True, check=True,
    )
    # qlmanage 输出文件名是 {原文件名}.png
    thumb = tmp_dir / f"{svg_path.name}.png"
    if not thumb.exists():
        # fallback: 大小写
        for f in tmp_dir.glob("*.png"):
            thumb = f
            break
    shutil.move(str(thumb), str(output))
    shutil.rmtree(tmp_dir)


def png_resize(source: Path, size: int, output: Path):
    """用 sips 将 PNG 缩放到指定尺寸。"""
    subprocess.run(
        ["sips", "-z", str(size), str(size), str(source), "--out", str(output)],
        capture_output=True, check=True,
    )


def generate_all(source: Path):
    if not source.exists():
        print(f"❌ 找不到文件: {source}")
        return 1

    is_svg = source.suffix.lower() == ".svg"
    resize = svg_to_png if is_svg else png_resize
    label = "SVG → PNG" if is_svg else "PNG 缩放"

    # 先转出 1024 的基准 PNG（后续步骤用）
    tmp_work = Path(tempfile.mkdtemp())
    base_png = tmp_work / "icon_1024.png"
    print(f"[0/3] {label}: {source.name} → 1024×1024 ...")
    resize(source, 1024, base_png)

    # 1. 生成多尺寸 PNG 图标集 → icon.icns
    print("[1/3] 生成 icon.icns ...")
    iconset = tmp_work / "icon.iconset"
    iconset.mkdir()

    for size in ICONSET_SIZES:
        # @1x
        png_resize(base_png, size, iconset / f"icon_{size}x{size}.png")
        # @2x
        double = size * 2
        if double <= 1024:
            png_resize(base_png, double, iconset / f"icon_{size}x{size}@2x.png")

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset),
         "-o", str(ROOT / "icon.icns")],
        check=True,
    )
    print(f"   ✅ icon.icns ({len(ICONSET_SIZES)} 尺寸 × @1x/@2x)")

    # 2. 复制 1024×1024 PNG 给应用运行时 Dock 图标
    print("[2/3] 生成 icon.png ...")
    shutil.copy(base_png, ROOT / "icon.png")
    print(f"   ✅ icon.png (1024×1024)")

    # 3. 生成 Windows .ico (多尺寸嵌入)
    print("[3/3] 生成 icon.ico ...")
    try:
        from PIL import Image

        img = Image.open(str(base_png))
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(str(ROOT / "icon.ico"), format="ICO", sizes=icon_sizes)
        print(f"   ✅ icon.ico ({len(icon_sizes)} 尺寸)")
    except ImportError:
        # 降级：用 sips 生成 ico（sips 对大 PNG 转 ico 有限制，先缩到 256）
        print("   ⚠️  未装 Pillow，降级为单尺寸 ico")
        ico_src = tmp_work / "icon_256.png"
        png_resize(base_png, 256, ico_src)
        subprocess.run(
            ["sips", "-s", "format", "ico", str(ico_src),
             "--out", str(ROOT / "icon.ico")],
            capture_output=True, check=True,
        )
        print("   ✅ icon.ico (256×256 单尺寸)")

    shutil.rmtree(tmp_work)

    print("\n✅ 全部图标生成完毕！")
    print("   重新打包: python3 build.py --dmg")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 generate_icons.py icon.svg")
        print("      python3 generate_icons.py icon_1024.png")
        sys.exit(1)

    source = Path(sys.argv[1])
    if not source.is_absolute():
        source = Path.cwd() / source
    sys.exit(generate_all(source))
