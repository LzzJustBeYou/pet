import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QMenu, qApp, QFileDialog
from PyQt5.QtCore import Qt, QPoint, QSize
from PyQt5.QtGui import QMovie

def resource_path(relative_path):
    """ 获取资源的绝对路径。兼容开发环境和 PyInstaller 打包后的环境 """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()
        
        # --- 宠物基础设置 ---
        self.pet_width = 100
        self.pet_height = 100
        
        # 记录当前的动图路径
        self.current_gif = resource_path('pet.gif')
        
        self.initUI()
        self.dragPosition = QPoint()

    def initUI(self):
        # 窗口和透明设置
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 标签设置
        self.label = QLabel(self)
        self.label.setFixedSize(self.pet_width, self.pet_height)
        self.resize(self.pet_width, self.pet_height)
        
        # 首次加载
        self.movie = QMovie(self.current_gif)
        self.movie.setScaledSize(QSize(self.pet_width, self.pet_height))
        self.label.setMovie(self.movie)
        self.movie.start()

    def change_pet(self, new_gif_path):
        """ 核心功能：平滑切换 GIF 动图 """
        self.movie.stop() # 停止旧动画
        self.current_gif = new_gif_path
        
        self.movie = QMovie(self.current_gif)
        self.movie.setScaledSize(QSize(self.pet_width, self.pet_height))
        self.label.setMovie(self.movie)
        self.movie.start() # 开始新动画

    # --- 鼠标左键拖拽功能 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragPosition = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.dragPosition)
            event.accept()

    # --- 强大的右键菜单功能 ---
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        # 1. 创建子菜单用于切换内置状态
        switch_menu = menu.addMenu("切换动作")
        action_chou = switch_menu.addAction("臭臭喵")
        action_work = switch_menu.addAction("工作喵")
        action_yaoyao = switch_menu.addAction("摇摇椅喵")
        action_music = switch_menu.addAction("听歌喵")
        
        # 分割线
        menu.addSeparator() 
        
        # 2. 自定义加载外部 GIF
        load_action = menu.addAction("加载本地 GIF...")
        
        # 分割线
        menu.addSeparator()
        
        # 3. 退出功能
        quit_action = menu.addAction("退出宠物")
        
        # 捕捉点击动作
        action = menu.exec_(self.mapToGlobal(event.pos()))
        
        # 根据用户的点击执行相应的逻辑
        if action == action_chou:
            self.change_pet(resource_path('pet.gif'))
        elif action == action_work:
            self.change_pet(resource_path('pet-3.gif'))
        elif action == action_yaoyao:
            self.change_pet(resource_path('pet-4.gif'))
        elif action == action_music:
            self.change_pet(resource_path('pet-5.gif'))
        elif action == load_action:
            # 弹出文件选择对话框
            file_name, _ = QFileDialog.getOpenFileName(
                self, "选择自定义宠物", "", "GIF 动图 (*.gif)"
            )
            if file_name: # 如果用户选了文件而不是点了取消
                self.change_pet(file_name)
        elif action == quit_action:
            qApp.quit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())