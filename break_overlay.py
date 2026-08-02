"""休息倒计时浮层（Health Reminder）。"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BreakOverlay(QWidget):
    skipped = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        # 必须带 Qt.Tool（含 Qt.Window），否则会变成父窗口的子控件，
        # 深色背景会直接盖在宠物贴图上形成"黑色蒙版"。
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self._total_seconds = 20
        self._fullscreen = False

        self._frame = QFrame(self)
        self._frame.setObjectName("breakOverlayFrame")
        self._apply_frame_style(self._frame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)
        self._build_layout()
        self.setFixedSize(300, 240)

    def show_break(
        self,
        kind: str,
        seconds: int,
        screen_geometry: QRect,
        fullscreen: bool = False,
    ) -> None:
        self._total_seconds = max(1, int(seconds))
        self._fullscreen = bool(fullscreen)
        if self._fullscreen:
            # 全屏=强制休息：窗口可被激活并接收按键，休息结束前无法跳过
            self.setAttribute(Qt.WA_ShowWithoutActivating, False)
            self.setFocusPolicy(Qt.StrongFocus)
        else:
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.setFocusPolicy(Qt.NoFocus)
        self._build_layout()
        self._apply_frame_style(self._frame)
        if kind == "long":
            self.title_label.setText("长休息，站起来走走")
            self.hint_label.setText("活动一下肩颈，看看窗外")
        else:
            self.title_label.setText("休息一下")
            self.hint_label.setText("看 20 英尺（6 米）外的远处")
        self.update_remaining(self._total_seconds)
        self._position_on(screen_geometry)
        self.show()
        self.raise_()
        if self._fullscreen:
            self.activateWindow()
            self.setFocus()

    def update_remaining(self, seconds: int) -> None:
        seconds = max(0, int(seconds))
        self.countdown_label.setText(self._format_countdown(seconds))
        self.progress.setRange(0, self._total_seconds)
        self.progress.setValue(seconds)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._skip()
            event.accept()
            return
        super().keyPressEvent(event)

    def _skip(self) -> None:
        self.hide()
        self.skipped.emit()

    def _format_countdown(self, seconds: int) -> str:
        if self._fullscreen:
            minutes, remaining = divmod(int(seconds), 60)
            return f"{minutes}:{remaining:02d}"
        return str(int(seconds))

    def _build_layout(self) -> None:
        old_layout = self._frame.layout()
        if old_layout is not None:
            # 同步摘除旧布局（deleteLater 是异步的，直接换新布局会报
            # "already has a layout"），并清掉旧控件，避免残留按钮。
            for widget in self._frame.findChildren(QWidget):
                widget.setParent(None)
                widget.hide()
                widget.deleteLater()
            detach = QWidget()
            detach.setLayout(old_layout)
            old_layout.deleteLater()

        layout = QVBoxLayout(self._frame)
        if self._fullscreen:
            layout.setContentsMargins(80, 40, 80, 48)
            layout.setSpacing(28)
            layout.insertStretch(0, 1)
        else:
            layout.setContentsMargins(24, 18, 24, 18)
            layout.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("breakTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        self.countdown_label = QLabel()
        self.countdown_label.setObjectName("breakCountdown")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.countdown_label)

        self.hint_label = QLabel()
        self.hint_label.setObjectName("breakHint")
        self.hint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.hint_label)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        self.skip_button = QPushButton("跳过本次")
        self.skip_button.setFocusPolicy(Qt.NoFocus)
        self.skip_button.clicked.connect(self._skip)
        if self._fullscreen:
            # 内容垂直居中，按钮靠屏幕下方水平居中（参考 Stretchly 底部操作区）
            layout.addStretch(1)
            layout.addWidget(self.skip_button, alignment=Qt.AlignHCenter)
        else:
            button_row = QHBoxLayout()
            button_row.addStretch(1)
            button_row.addWidget(self.skip_button)
            layout.addLayout(button_row)

    def _position_on(self, geometry: QRect) -> None:
        if self._fullscreen:
            self.setFixedSize(geometry.width(), geometry.height())
            self.move(geometry.x(), geometry.y())
        else:
            self.setFixedSize(300, 240)
            x = geometry.x() + (geometry.width() - self.width()) // 2
            y = geometry.y() + (geometry.height() - self.height()) // 2
            self.move(max(geometry.x(), x), max(geometry.y(), y))

    def _apply_frame_style(self, frame: QFrame) -> None:
        if self._fullscreen:
            frame.setStyleSheet(
                """
                QFrame#breakOverlayFrame {
                    background: rgba(15, 15, 15, 255);
                    border: none;
                    border-radius: 0;
                }
                QLabel#breakTitle {
                    color: white;
                    font-size: 38px;
                    font-weight: 300;
                }
                QLabel#breakCountdown {
                    color: #ffd166;
                    font-size: 150px;
                    font-weight: 200;
                }
                QLabel#breakHint {
                    color: rgba(255, 255, 255, 170);
                    font-size: 24px;
                }
                QPushButton {
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 70);
                    border-radius: 8px;
                    padding: 10px 32px;
                    background: rgba(255, 255, 255, 30);
                    font-size: 16px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 55);
                }
                QProgressBar {
                    border: none;
                    border-radius: 4px;
                    background: rgba(255, 255, 255, 30);
                    height: 8px;
                }
                QProgressBar::chunk {
                    border-radius: 4px;
                    background: #4cafa1;
                }
                """
            )
        else:
            frame.setStyleSheet(
                """
                QFrame#breakOverlayFrame {
                    background: rgba(34, 34, 34, 240);
                    border: 2px solid rgba(255, 255, 255, 90);
                    border-radius: 14px;
                }
                QLabel#breakTitle {
                    color: white;
                    font-size: 18px;
                    font-weight: 700;
                }
                QLabel#breakCountdown {
                    color: #ffd166;
                    font-size: 44px;
                    font-weight: 700;
                }
                QLabel#breakHint {
                    color: rgba(255, 255, 255, 170);
                    font-size: 13px;
                }
                QPushButton {
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 70);
                    border-radius: 8px;
                    padding: 6px 16px;
                    background: rgba(255, 255, 255, 30);
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 55);
                }
                QProgressBar {
                    border: none;
                    border-radius: 4px;
                    background: rgba(255, 255, 255, 30);
                    height: 8px;
                }
                QProgressBar::chunk {
                    border-radius: 4px;
                    background: #4cafa1;
                }
                """
            )
