"""DesktopPet Windows 安装器 —— 负责将宠物安装到 Windows 系统。

由 PyInstaller 打包成 DesktopPet_Setup.exe，内嵌 dist/DesktopPet/ 作为 app_data。
运行时提供 GUI 引导用户选择安装路径、创建快捷方式、写入注册表。
"""

import os
import sys
import shutil
import subprocess
import winreg

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox,
    QProgressBar, QFileDialog, QMessageBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon

from autostart import write_windows_run_entry

APP_NAME = "DesktopPet"
APP_DISPLAY_NAME = "桌面宠物 DesktopPet"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def resource_path(relative_path):
    """获取内嵌资源的绝对路径。兼容开发环境和 PyInstaller --onefile。"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ---------------------------------------------------------------------------
# 安装工作线程
# ---------------------------------------------------------------------------

class InstallThread(QThread):
    """后台执行安装步骤，通过信号更新 UI。"""
    progress = pyqtSignal(int, str)   # percentage, status message
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, install_dir, create_start_menu, create_desktop, auto_start):
        super().__init__()
        self.install_dir = install_dir
        self.create_start_menu = create_start_menu
        self.create_desktop = create_desktop
        self.auto_start = auto_start

    def run(self):
        try:
            app_source = resource_path("app_data")
            exe_path = os.path.join(self.install_dir, f"{APP_NAME}.exe")

            # ── Step 1: 复制文件 (0→60%) ──
            self.progress.emit(5, "正在准备安装目录...")
            if os.path.exists(self.install_dir):
                shutil.rmtree(self.install_dir)

            self.progress.emit(10, "正在复制文件...")
            shutil.copytree(app_source, self.install_dir)
            self.progress.emit(60, "文件复制完成")

            # ── Step 2: 快捷方式 (60→80%) ──
            if self.create_start_menu:
                self.progress.emit(65, "正在创建开始菜单快捷方式...")
                self._create_shortcut("start_menu", exe_path)
            if self.create_desktop:
                self.progress.emit(75, "正在创建桌面快捷方式...")
                self._create_shortcut("desktop", exe_path)
            self.progress.emit(80, "快捷方式创建完成")

            # ── Step 3: 注册表 (80→95%) ──
            self.progress.emit(85, "正在写入注册表...")
            self._write_uninstall_registry(exe_path)
            if self.auto_start:
                self._write_autostart_registry(exe_path)
            self.progress.emit(95, "注册表写入完成")

            # ── Step 4: 生成卸载器 (95→100%) ──
            self.progress.emit(97, "正在生成卸载程序...")
            self._generate_uninstall_bat()
            self.progress.emit(100, "安装完成！")

            self.finished.emit(True, "")

        except Exception as e:
            self.finished.emit(False, str(e))

    # ── 快捷方式 ──

    def _create_shortcut(self, kind, target_path):
        """通过 PowerShell COM 创建 .lnk 快捷方式。"""
        if kind == "start_menu":
            lnk_dir = os.path.join(
                os.environ["APPDATA"],
                "Microsoft", "Windows", "Start Menu", "Programs",
            )
        else:
            lnk_dir = os.path.join(os.environ["USERPROFILE"], "Desktop")

        shortcut_path = os.path.join(lnk_dir, f"{APP_NAME}.lnk")

        # 删除已有
        if os.path.exists(shortcut_path):
            os.remove(shortcut_path)

        # 图标
        icon_path = os.path.join(self.install_dir, "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = target_path  # fallback 到 exe 内嵌图标

        # 使用 PowerShell COM - 这是 Windows 上创建 .lnk 最可靠的方式
        ps = (
            f'$ws = New-Object -ComObject WScript.Shell;'
            f'$s = $ws.CreateShortcut("{shortcut_path}");'
            f'$s.TargetPath = "{target_path}";'
            f'$s.WorkingDirectory = "{self.install_dir}";'
            f'$s.IconLocation = "{icon_path}";'
            f'$s.Save()'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"创建快捷方式失败: {result.stderr}")

    # ── 注册表 ──

    def _write_uninstall_registry(self, exe_path):
        """写入卸载信息，使应用出现在 Windows 设置 → 应用和功能中。"""
        uninstall_bat = os.path.join(self.install_dir, "uninstall.bat")
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\DesktopPet"

        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_DISPLAY_NAME)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninstall_bat)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, self.install_dir)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, exe_path)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "DesktopPet")
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
        except Exception as e:
            raise RuntimeError(f"写入卸载注册表失败: {e}")

    def _write_autostart_registry(self, exe_path):
        """写入 Run 键实现开机自启。"""
        write_windows_run_entry(exe_path)

    # ── 卸载脚本 ──

    def _generate_uninstall_bat(self):
        """在安装目录下生成 uninstall.bat。

        卸载步骤：
        1. 结束宠物进程
        2. 删除快捷方式
        3. 删除注册表项
        4. 延迟删除安装目录自身（生成临时脚本调度删除）
        """
        start_menu_lnk = os.path.join(
            os.environ["APPDATA"],
            "Microsoft", "Windows", "Start Menu", "Programs",
            f"{APP_NAME}.lnk",
        )
        desktop_lnk = os.path.join(
            os.environ["USERPROFILE"], "Desktop",
            f"{APP_NAME}.lnk",
        )

        bat = (
            '@echo off\r\n'
            'title 卸载 DesktopPet\r\n'
            'echo 正在卸载 DesktopPet...\r\n'
            '\r\n'
            ':: 结束进程\r\n'
            f'taskkill /f /im {APP_NAME}.exe 2>nul\r\n'
            '\r\n'
            ':: 删除开始菜单快捷方式\r\n'
            f'del /f /q "{start_menu_lnk}" 2>nul\r\n'
            '\r\n'
            ':: 删除桌面快捷方式\r\n'
            f'del /f /q "{desktop_lnk}" 2>nul\r\n'
            '\r\n'
            ':: 删除自启动注册表\r\n'
            f'reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" '
            f'/v "{APP_NAME}" /f 2>nul\r\n'
            '\r\n'
            ':: 删除卸载注册表\r\n'
            f'reg delete '
            f'"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" '
            f'/f 2>nul\r\n'
            '\r\n'
            ':: 生成临时清理脚本，延迟 2 秒后删除安装目录并自毁\r\n'
            '(\r\n'
            'echo @echo off\r\n'
            'echo ping 127.0.0.1 -n 3 ^>nul\r\n'
            f'echo rmdir /s /q "{self.install_dir}"\r\n'
            'echo del /f /q "%%~f0"\r\n'
            f') > "%TEMP%\\cleanup_desktoppet.bat"\r\n'
            '\r\n'
            f'start "" /b "%TEMP%\\cleanup_desktoppet.bat"\r\n'
            'echo 卸载完成！\r\n'
            'ping 127.0.0.1 -n 2 >nul\r\n'
        )

        bat_path = os.path.join(self.install_dir, "uninstall.bat")
        # 使用 GBK 编码确保中文 Windows 上正确显示
        with open(bat_path, "w", encoding="gbk") as f:
            f.write(bat)


# ---------------------------------------------------------------------------
# 安装器主界面
# ---------------------------------------------------------------------------

class InstallerWindow(QWidget):
    """安装器 GUI 窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_DISPLAY_NAME} 安装程序")
        self.setFixedSize(480, 340)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowMinimizeButtonHint
        )
        self._install_thread = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(28, 24, 28, 24)

        # ── 标题 ──
        title = QLabel(f"🐾 {APP_DISPLAY_NAME}")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # ── 安装路径 ──
        layout.addWidget(QLabel("安装路径:"))
        path_row = QHBoxLayout()
        default_path = os.path.join(
            os.environ.get("LOCALAPPDATA", os.environ["USERPROFILE"]),
            "Programs", APP_NAME,
        )
        self.path_input = QLineEdit(default_path)
        path_row.addWidget(self.path_input)

        browse_btn = QPushButton("浏览...")
        browse_btn.setFixedWidth(64)
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        # ── 选项 ──
        self.cb_start_menu = QCheckBox("创建开始菜单快捷方式")
        self.cb_start_menu.setChecked(True)
        layout.addWidget(self.cb_start_menu)

        self.cb_desktop = QCheckBox("创建桌面快捷方式")
        self.cb_desktop.setChecked(True)
        layout.addWidget(self.cb_desktop)

        self.cb_autostart = QCheckBox("开机自动启动")
        layout.addWidget(self.cb_autostart)

        # ── 进度条 ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)

        # ── 按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.install_btn = QPushButton("  安  装  ")
        self.install_btn.setFixedSize(120, 36)
        self.install_btn.setStyleSheet(
            "QPushButton { font-size: 14px; font-weight: bold; }"
        )
        self.install_btn.clicked.connect(self._start_install)
        btn_row.addWidget(self.install_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()
        self.setLayout(layout)

    # ── 交互 ──

    def _browse_path(self):
        chosen = QFileDialog.getExistingDirectory(self, "选择安装目录")
        if chosen:
            self.path_input.setText(os.path.join(chosen, APP_NAME))

    def _start_install(self):
        install_dir = self.path_input.text().strip()
        if not install_dir:
            QMessageBox.warning(self, "提示", "请输入安装路径")
            return

        # 确认覆盖
        if os.path.exists(install_dir):
            reply = QMessageBox.question(
                self, "确认",
                f"目录已存在:\n{install_dir}\n\n是否覆盖安装？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        # 锁定 UI
        self.install_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # 启动后台安装
        self._install_thread = InstallThread(
            install_dir,
            self.cb_start_menu.isChecked(),
            self.cb_desktop.isChecked(),
            self.cb_autostart.isChecked(),
        )
        self._install_thread.progress.connect(self._on_progress)
        self._install_thread.finished.connect(self._on_finished)
        self._install_thread.start()

    def _on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def _on_finished(self, success, error_msg):
        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText("安装完成！")
            QMessageBox.information(
                self, "安装完成",
                f"DesktopPet 已成功安装到:\n{self.path_input.text().strip()}\n\n"
                "你可以从开始菜单启动宠物了！",
            )
            QApplication.quit()
        else:
            self.install_btn.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.status_label.setText("")
            QMessageBox.critical(self, "安装失败", f"安装过程中出现错误:\n\n{error_msg}")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)

    # 尝试设置安装器图标
    icon_path = resource_path(os.path.join("app_data", "icon.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = InstallerWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
