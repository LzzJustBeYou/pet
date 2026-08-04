from __future__ import annotations

from datetime import datetime
from typing import Optional

from PyQt5.QtCore import QPoint, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from holiday_calendar import HolidayCalendar
from todo_models import TodoOccurrence, local_now, time_to_text
from todo_store import TodoStore
from todo_ui_common import occurrence_is_due_at


class TodoQuickPanel(QWidget):
    manage_requested = pyqtSignal(object)
    visibility_changed = pyqtSignal(bool)

    def __init__(
        self,
        store: TodoStore,
        work_calendar: HolidayCalendar,
        parent=None,
        visible_ms: int = 12000,
        max_items: int = 4,
    ):
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self.store = store
        self.work_calendar = work_calendar
        self.visible_ms = visible_ms
        self.max_items = max(1, max_items)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.NoFocus)

        frame = QFrame(self)
        frame.setObjectName("quickPanelFrame")
        frame.setStyleSheet(
            """
            QFrame#quickPanelFrame {
                background: rgba(34, 34, 34, 232);
                border: 1px solid rgba(255, 255, 255, 80);
                border-radius: 10px;
            }
            QLabel {
                color: white;
            }
            QLabel#quickSubtitle {
                color: rgba(255, 255, 255, 185);
            }
            QLabel#quickCount {
                background: #e84b4b;
                color: white;
                border-radius: 9px;
                padding: 1px 6px;
                font-weight: 700;
            }
            QPushButton {
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QPushButton#quickItem {
                background: transparent;
                text-align: left;
            }
            QPushButton#quickItem:hover {
                background: rgba(255, 255, 255, 28);
            }
            QPushButton#quickManage {
                background: rgba(255, 255, 255, 36);
                font-weight: 600;
            }
            QPushButton#quickManage:hover {
                background: rgba(255, 255, 255, 56);
            }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        header = QHBoxLayout()
        self.title_label = QLabel("Todo")
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.count_label = QLabel()
        self.count_label.setObjectName("quickCount")
        self.count_label.hide()
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.count_label)
        layout.addLayout(header)

        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("quickSubtitle")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)

        self.items_layout = QVBoxLayout()
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(2)
        layout.addLayout(self.items_layout)

        self.manage_button = QPushButton("管理待办")
        self.manage_button.setObjectName("quickManage")
        self.manage_button.setFocusPolicy(Qt.NoFocus)
        self.manage_button.clicked.connect(
            lambda _checked=False: self._request_manage(None)
        )
        layout.addWidget(self.manage_button)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def toggle_near(self, anchor: QWidget) -> None:
        if self.isVisible():
            self.hide()
            return
        self.show_near(anchor)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    def show_near(self, anchor: QWidget) -> None:
        self.refresh()
        self.adjustSize()
        self._position_near(anchor)
        self.show()
        self.raise_()
        self._hide_timer.start(self.visible_ms)

    def reposition_near(self, anchor: QWidget) -> None:
        if not self.isVisible():
            return
        self._position_near(anchor)

    def refresh(self) -> None:
        now = local_now()
        self._clear_items()
        try:
            occurrences = self.store.list_today(now.date(), self.work_calendar)
        except Exception as exc:
            self.count_label.hide()
            self.subtitle_label.setText(f"读取待办失败：{exc}")
            return

        due_occurrences = [
            item for item in occurrences if occurrence_is_due_at(item, now)
        ]
        due_count = len(due_occurrences)
        if due_count:
            self.count_label.setText("99+" if due_count > 99 else str(due_count))
            self.count_label.show()
        else:
            self.count_label.hide()

        overdue_count = sum(
            1
            for item in due_occurrences
            if item.due_date is not None and item.due_date < now.date()
        )
        timed_due_count = sum(
            1
            for item in due_occurrences
            if item.due_date == now.date()
            and item.due_time is not None
            and item.due_time <= now.time().replace(second=0, microsecond=0)
        )
        date_only_count = sum(1 for item in due_occurrences if item.due_time is None)

        if due_count:
            parts = []
            if timed_due_count:
                parts.append(f"{timed_due_count} 个已到时间")
            if overdue_count:
                parts.append(f"{overdue_count} 个逾期")
            if date_only_count:
                parts.append(f"{date_only_count} 个全天")
            self.subtitle_label.setText(" · ".join(parts))
        else:
            self.subtitle_label.setText("目前没有已到提醒的待办。")

        for occurrence in due_occurrences[: self.max_items]:
            self._add_occurrence_button(occurrence, now)

        remaining = due_count - self.max_items
        if remaining > 0:
            more_button = QPushButton(f"还有 {remaining} 个，打开管理页查看")
            more_button.setObjectName("quickItem")
            more_button.setFocusPolicy(Qt.NoFocus)
            more_button.clicked.connect(
                lambda _checked=False: self._request_manage(None)
            )
            self.items_layout.addWidget(more_button)

    def enterEvent(self, event) -> None:
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hide_timer.start(self.visible_ms)
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def _add_occurrence_button(self, occurrence: TodoOccurrence, now: datetime) -> None:
        button = QPushButton(self._occurrence_text(occurrence, now))
        button.setObjectName("quickItem")
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(
            lambda _checked=False, occurrence_id=occurrence.id: self._request_manage(
                occurrence_id
            )
        )
        self.items_layout.addWidget(button)

    def _clear_items(self) -> None:
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _request_manage(self, occurrence_id: Optional[int]) -> None:
        self.hide()
        self.manage_requested.emit(occurrence_id)

    def _occurrence_text(self, occurrence: TodoOccurrence, now) -> str:
        if occurrence.due_date is None:
            return f"便签  {occurrence.title}"
        if occurrence.due_date < now.date():
            prefix = occurrence.due_date.strftime("逾期 %m-%d")
        elif occurrence.due_time is None:
            prefix = "今天"
        else:
            time_text = time_to_text(occurrence.due_time) or ""
            if occurrence.due_time <= now.time().replace(second=0, microsecond=0):
                prefix = f"已到 {time_text}"
            else:
                prefix = time_text
        return f"{prefix}  {occurrence.title}"

    def _position_near(self, anchor: QWidget) -> None:
        anchor_center = anchor.mapToGlobal(anchor.rect().center())
        screen = QApplication.screenAt(anchor_center)
        if screen is None:
            screen = QApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen is not None else None
        anchor_top_left = anchor.mapToGlobal(QPoint(0, 0))
        target = QPoint(anchor_top_left.x() + anchor.width() + 8, anchor_top_left.y())
        if geometry is not None:
            if target.x() + self.width() > geometry.right():
                target.setX(anchor_top_left.x() - self.width() - 8)
            if target.y() + self.height() > geometry.bottom():
                target.setY(geometry.bottom() - self.height())
            target.setX(max(geometry.left(), target.x()))
            target.setY(max(geometry.top(), target.y()))
        self.move(target)
