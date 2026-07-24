import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QMenu, qApp, QFileDialog
from PyQt5.QtCore import Qt, QPoint, QSize
from PyQt5.QtGui import QMovie, QIcon


def resource_path(relative_path):
    """获取资源的绝对路径。兼容开发环境和 PyInstaller 打包后的环境"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def scan_actions(actions_dir="actions"):
    """
    扫描 actions/ 目录，自动发现所有动作。
    约定：子目录 = 分类（菜单），目录内的 .gif 文件 = 动作，文件名（去扩展名）= 显示名。

    返回: [(分类名, [(显示名, 完整路径), ...]), ...]
    只需把 GIF 放进 actions/ 的任意子目录即可自动出现在菜单中。
    """
    categories = []
    target_dir = resource_path(actions_dir)
    if not os.path.isdir(target_dir):
        return categories

    for category in sorted(os.listdir(target_dir)):
        cat_path = os.path.join(target_dir, category)
        if not os.path.isdir(cat_path):
            continue
        actions = []
        for f in sorted(os.listdir(cat_path)):
            if f.lower().endswith(".gif"):
                full_path = os.path.join(cat_path, f)
                display_name = os.path.splitext(f)[0]
                actions.append((display_name, full_path))
        if actions:
            categories.append((category, actions))
    return categories


class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        # --- 宠物基础设置 ---
        self.pet_width = 100
        self.pet_height = 100

        # 自动发现所有动作，默认"臭臭小八"，找不到则取第一个
        DEFAULT_PET = "臭臭小八"
        all_actions = scan_actions()
        self.current_gif = None
        for _cat, actions in all_actions:
            for name, path in actions:
                if name == DEFAULT_PET:
                    self.current_gif = path
                    break
            if self.current_gif:
                break
        if not self.current_gif and all_actions and all_actions[0][1]:
            self.current_gif = all_actions[0][1][0][1]

        self.initUI()
        self.dragPosition = QPoint()

    def initUI(self):
        # 窗口和透明设置
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 标签设置
        self.label = QLabel(self)
        self.label.setFixedSize(self.pet_width, self.pet_height)
        self.resize(self.pet_width, self.pet_height)

        # 首次加载
        if self.current_gif:
            self._load_gif(self.current_gif)

    def _load_gif(self, gif_path):
        """加载并播放 GIF"""
        self.movie = QMovie(gif_path)
        self.movie.setScaledSize(QSize(self.pet_width, self.pet_height))
        self.label.setMovie(self.movie)
        self.movie.start()

    def change_pet(self, new_gif_path):
        """核心功能：平滑切换 GIF 动图"""
        self.movie.stop()
        self.current_gif = new_gif_path
        self._load_gif(new_gif_path)

    # --- 鼠标左键拖拽功能 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragPosition = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.dragPosition)
            event.accept()

    # --- 右键菜单功能 ---
    def contextMenuEvent(self, event):
        menu = QMenu(self)

        # 动态扫描，构建分类子菜单
        categories = scan_actions()
        for cat_name, actions in categories:
            sub_menu = menu.addMenu(cat_name)
            for display_name, gif_path in actions:
                action = sub_menu.addAction(display_name)
                action.setData(gif_path)

        menu.addSeparator()
        load_action = menu.addAction("加载本地 GIF...")
        menu.addSeparator()
        quit_action = menu.addAction("退出宠物")

        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action is None:
            return

        if action == load_action:
            file_name, _ = QFileDialog.getOpenFileName(
                self, "选择自定义宠物", "", "GIF 动图 (*.gif)"
            )
            if file_name:
                self.change_pet(file_name)
        elif action == quit_action:
            qApp.quit()
        elif action.data() is not None:
            self.change_pet(action.data())


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 设置应用图标（显示在任务栏 / Dock / Alt+Tab 切换器中）
    icon_path = resource_path("icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())
