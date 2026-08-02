"""跨平台开机自启管理（M1）。

macOS 使用 LaunchAgent plist，Windows 使用 HKCU Run 注册表键，
Linux 使用 XDG autostart 桌面文件。安装器与运行时共用本模块，
避免平台逻辑重复实现。
"""

from __future__ import annotations

import os
import plistlib
import sys
from pathlib import Path
from typing import List


APP_NAME = "DesktopPet"
APP_LABEL = "com.petapp.desktoppet"


def command_for_autostart() -> List[str]:
    """返回开机自启要执行的命令行。"""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    script = Path(__file__).resolve().parent / "main.py"
    return [sys.executable, str(script)]


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------


def macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{APP_LABEL}.plist"


def macos_plist_content(command: List[str]) -> bytes:
    payload = {
        "Label": APP_LABEL,
        "ProgramArguments": list(command),
        "RunAtLoad": True,
        "ProcessType": "Interactive",
    }
    return plistlib.dumps(payload)


def _set_macos_autostart(enabled: bool) -> None:
    path = macos_plist_path()
    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(macos_plist_content(command_for_autostart()))
        elif path.exists():
            path.unlink()
    except OSError as exc:
        raise RuntimeError(f"写入开机自启配置失败: {exc}") from exc


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------


def windows_run_key_path() -> str:
    return r"Software\Microsoft\Windows\CurrentVersion\Run"


def write_windows_run_entry(exe_path: str) -> None:
    """写入 Run 键（供安装器与运行时共用）。"""
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            windows_run_key_path(),
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, str(exe_path))
    except OSError as exc:
        raise RuntimeError(f"写入自启动注册表失败: {exc}") from exc


def _windows_autostart_value() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            windows_run_key_path(),
        ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return str(value)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError(f"读取自启动注册表失败: {exc}") from exc


def _set_windows_autostart(enabled: bool) -> None:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            windows_run_key_path(),
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, APP_NAME, 0, winreg.REG_SZ, sys.executable
                )
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        raise RuntimeError(f"写入自启动注册表失败: {exc}") from exc


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------


def linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / f"{APP_NAME}.desktop"


def linux_desktop_content(command: List[str]) -> str:
    exec_line = " ".join(f'"{part}"' for part in command)
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Exec={exec_line}\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _set_linux_autostart(enabled: bool) -> None:
    path = linux_desktop_path()
    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                linux_desktop_content(command_for_autostart()),
                encoding="utf-8",
            )
        elif path.exists():
            path.unlink()
    except OSError as exc:
        raise RuntimeError(f"写入自启动配置失败: {exc}") from exc


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------


def set_autostart(enabled: bool) -> None:
    """启用/禁用开机自启；失败抛出 RuntimeError。"""
    if sys.platform == "darwin":
        _set_macos_autostart(enabled)
    elif sys.platform == "win32":
        _set_windows_autostart(enabled)
    elif sys.platform.startswith("linux"):
        _set_linux_autostart(enabled)
    else:
        raise RuntimeError(f"当前平台不支持开机自启: {sys.platform}")


def is_autostart_enabled() -> bool:
    if sys.platform == "darwin":
        return macos_plist_path().is_file()
    if sys.platform == "win32":
        return _windows_autostart_value() is not None
    if sys.platform.startswith("linux"):
        return linux_desktop_path().is_file()
    return False
