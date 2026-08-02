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
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self._total_seconds = 20

        frame = QFrame(self)
        frame.setObjectName("breakOverlayFrame")
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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        layout = QVBoxLayout(frame)
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

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.skip_button = QPushButton("跳过本次")
        self.skip_button.setFocusPolicy(Qt.NoFocus)
        self.skip_button.clicked.connect(self._skip)
        button_row.addWidget(self.skip_button)
        layout.addLayout(button_row)

        self.setFixedSize(300, 240)

    def show_break(
        self,
        kind: str,
        seconds: int,
        screen_geometry: QRect,
    ) -> None:
        self._total_seconds = max(1, int(seconds))
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

    def update_remaining(self, seconds: int) -> None:
        seconds = max(0, int(seconds))
        self.countdown_label.setText(str(seconds))
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

    def _position_on(self, geometry: QRect) -> None:
        x = geometry.x() + (geometry.width() - self.width()) // 2
        y = geometry.y() + (geometry.height() - self.height()) // 2
        self.move(max(geometry.x(), x), max(geometry.y(), y))
