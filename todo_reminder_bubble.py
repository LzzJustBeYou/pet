from __future__ import annotations

from PyQt5.QtCore import QPoint, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from todo_models import TodoOccurrence, time_to_text

class TodoReminderBubble(QWidget):
    clicked = pyqtSignal(object)

    def __init__(self, parent=None, visible_ms: int = 8000):
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self.visible_ms = visible_ms
        self._occurrences: list[TodoOccurrence] = []
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.NoFocus)

        frame = QFrame(self)
        frame.setObjectName("bubbleFrame")
        frame.setStyleSheet(
            """
            QFrame#bubbleFrame {
                background: rgba(34, 34, 34, 230);
                border: 1px solid rgba(255, 255, 255, 80);
                border-radius: 8px;
            }
            QLabel {
                color: white;
            }
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: 600;")
        self.title_label.setWordWrap(True)
        self.time_label = QLabel()
        layout.addWidget(self.title_label)
        layout.addWidget(self.time_label)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_for_occurrences(self, occurrences: list[TodoOccurrence], anchor: QWidget) -> None:
        if not occurrences:
            return
        self._occurrences = occurrences
        if len(occurrences) == 1:
            occurrence = occurrences[0]
            self.title_label.setText(occurrence.title)
            self.time_label.setText(self._time_text(occurrence))
        else:
            first = occurrences[0]
            self.title_label.setText(f"{len(occurrences)} 个待办已到时间")
            self.time_label.setText(f"{self._time_text(first)} 等")
        self.adjustSize()
        self._position_near(anchor)
        self.show()
        self._hide_timer.start(self.visible_ms)

    def enterEvent(self, event) -> None:
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hide_timer.start(self.visible_ms)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            occurrence_id = self._occurrences[0].id if self._occurrences else None
            self.clicked.emit(occurrence_id)
            self.hide()
            event.accept()
            return
        super().mousePressEvent(event)

    def _time_text(self, occurrence: TodoOccurrence) -> str:
        if occurrence.due_date is None:
            return "无日期"
        value = time_to_text(occurrence.due_time) or "全天"
        return f"{occurrence.due_date.isoformat()} {value}"

    def _position_near(self, anchor: QWidget) -> None:
        screen = QApplication.screenAt(anchor.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen is not None else None
        target = QPoint(anchor.x() + anchor.width() + 8, anchor.y())
        if geometry is not None:
            if target.x() + self.width() > geometry.right():
                target.setX(anchor.x() - self.width() - 8)
            if target.y() + self.height() > geometry.bottom():
                target.setY(geometry.bottom() - self.height())
            target.setX(max(geometry.left(), target.x()))
            target.setY(max(geometry.top(), target.y()))
        self.move(target)
