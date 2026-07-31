from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from PyQt5.QtCore import QDate, QPoint, QSignalBlocker, QTimer, Qt, QTime, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from holiday_calendar import (
    CalendarDataError,
    HolidayCalendar,
    save_user_calendar,
)
from todo_models import (
    RECURRENCE_DAILY,
    RECURRENCE_EVERY_N_DAYS,
    RECURRENCE_MONTHLY,
    RECURRENCE_NONE,
    RECURRENCE_WEEKLY,
    RECURRENCE_YEARLY,
    STATUS_COMPLETED,
    TodoOccurrence,
    local_now,
    time_to_text,
)
from todo_store import TodoStore, TodoValidationError


RECURRENCE_ITEMS = [
    ("不重复", RECURRENCE_NONE),
    ("每天", RECURRENCE_DAILY),
    ("每周", RECURRENCE_WEEKLY),
    ("每月", RECURRENCE_MONTHLY),
    ("每年", RECURRENCE_YEARLY),
    ("每 N 天", RECURRENCE_EVERY_N_DAYS),
]
TIME_STEP_MINUTES = 5


def _to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _from_qdate(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def _to_qtime(value: Optional[time]) -> QTime:
    if value is None:
        now = local_now()
        value = snap_time_to_step(time(now.hour, now.minute))
    return QTime(value.hour, value.minute)


def _from_qtime(value: QTime) -> time:
    return time(value.hour(), value.minute())


def snap_time_to_step(
    value: time,
    step_minutes: int = TIME_STEP_MINUTES,
    round_up: bool = True,
) -> time:
    step_minutes = max(1, min(60, int(step_minutes)))
    total_minutes = value.hour * 60 + value.minute
    if total_minutes % step_minutes:
        if round_up:
            total_minutes = ((total_minutes // step_minutes) + 1) * step_minutes
        else:
            total_minutes = round(total_minutes / step_minutes) * step_minutes
    total_minutes = min(total_minutes, 23 * 60 + (60 - step_minutes))
    return time(total_minutes // 60, total_minutes % 60)


def calendar_errors_are_not_found(errors: list[str]) -> bool:
    return bool(errors) and all("not found" in error.lower() for error in errors)


def occurrence_is_due_at(occurrence: TodoOccurrence, now: datetime) -> bool:
    if occurrence.status == STATUS_COMPLETED:
        return False
    if occurrence.due_date is None:
        return False
    if occurrence.due_date < now.date():
        return True
    if occurrence.due_date > now.date():
        return False
    if occurrence.due_time is None:
        return True
    return occurrence.due_time <= now.time().replace(second=0, microsecond=0)


class SteppedTimeEdit(QTimeEdit):
    def __init__(self, parent=None, step_minutes: int = TIME_STEP_MINUTES):
        super().__init__(parent)
        self.step_minutes = step_minutes
        self.editingFinished.connect(self.snap_to_step)

    def stepBy(self, steps: int) -> None:
        current = snap_time_to_step(_from_qtime(self.time()), self.step_minutes)
        total_minutes = current.hour * 60 + current.minute + steps * self.step_minutes
        total_minutes = max(0, min(23 * 60 + (60 - self.step_minutes), total_minutes))
        self.setTime(QTime(total_minutes // 60, total_minutes % 60))

    def snap_to_step(self) -> None:
        snapped = snap_time_to_step(_from_qtime(self.time()), self.step_minutes)
        self.setTime(QTime(snapped.hour, snapped.minute))


class TodoQuickPanel(QWidget):
    manage_requested = pyqtSignal(object)

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


class TodoManagerWindow(QWidget):
    todos_changed = pyqtSignal()
    calendar_changed = pyqtSignal()

    def __init__(
        self,
        store: TodoStore,
        work_calendar: HolidayCalendar,
        parent=None,
    ):
        super().__init__(parent, Qt.Window)
        self.store = store
        self.work_calendar = work_calendar
        self._selected_occurrence_id: Optional[int] = None
        self._refreshing = False
        self._network_manager: Optional[QNetworkAccessManager] = None
        self._pending_calendar_urls: list[str] = []
        self._calendar_update_errors: list[str] = []
        self._current_calendar_update_url = ""

        self.setWindowTitle("Todo")
        self.resize(780, 520)
        self._init_ui()
        self.start_new()
        self.refresh()

    def _init_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        toolbar = QHBoxLayout()
        title = QLabel("Todo")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.add_button = QPushButton("新增")
        self.add_button.clicked.connect(self.start_new)
        toolbar.addWidget(self.add_button)

        self.calendar_button = QToolButton()
        self.calendar_button.setText("日历")
        self.calendar_button.setPopupMode(QToolButton.InstantPopup)
        self.calendar_button.setToolTip("更新中国大陆工作日日历")
        self.calendar_menu = QMenu(self.calendar_button)
        self.calendar_button.setMenu(self.calendar_menu)
        toolbar.addWidget(self.calendar_button)
        outer.addLayout(toolbar)

        self.splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(self.splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.today_list = self._make_list()
        self.undated_list = self._make_list()
        self.planned_list = self._make_list()
        self.completed_list = self._make_list()
        self.tabs.addTab(self.today_list, "今天")
        self.tabs.addTab(self.undated_list, "便签")
        self.tabs.addTab(self.planned_list, "计划")
        self.tabs.addTab(self.completed_list, "已完成")
        self.tabs.currentChanged.connect(self._tab_changed)
        left_layout.addWidget(self.tabs)
        self.splitter.addWidget(left)

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(8, 0, 0, 0)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("标题")
        form.addRow("标题", self.title_edit)

        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("备注")
        self.note_edit.setFixedHeight(90)
        form.addRow("备注", self.note_edit)

        due_row = QHBoxLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setMinimumDate(QDate(2000, 1, 1))
        self.date_edit.setMaximumDate(QDate(9999, 12, 31))
        due_row.addWidget(self.date_edit)
        self.no_date_check = QCheckBox("无日期")
        self.no_date_check.toggled.connect(self._sync_date_controls)
        due_row.addWidget(self.no_date_check)
        self.has_time_check = QCheckBox("时间")
        self.has_time_check.toggled.connect(self._sync_time_enabled)
        due_row.addWidget(self.has_time_check)
        self.time_edit = SteppedTimeEdit(step_minutes=TIME_STEP_MINUTES)
        self.time_edit.setDisplayFormat("HH:mm")
        due_row.addWidget(self.time_edit)
        due_row.addStretch()
        form.addRow("日期", due_row)

        recurrence_row = QHBoxLayout()
        self.recurrence_combo = QComboBox()
        for label, value in RECURRENCE_ITEMS:
            self.recurrence_combo.addItem(label, value)
        self.recurrence_combo.currentIndexChanged.connect(self._sync_recurrence_controls)
        recurrence_row.addWidget(self.recurrence_combo)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 365)
        self.interval_spin.setValue(1)
        self.interval_spin.setSuffix(" 天")
        recurrence_row.addWidget(self.interval_spin)
        recurrence_row.addStretch()
        form.addRow("重复", recurrence_row)

        self.skip_holidays_check = QCheckBox("跳过节假日")
        self.skip_holidays_check.toggled.connect(self._sync_calendar_limits)
        form.addRow("", self.skip_holidays_check)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem("本次及之后", "future")
        self.scope_combo.addItem("仅本次", "single")
        self.scope_combo.currentIndexChanged.connect(self._sync_scope_controls)
        form.addRow("编辑", self.scope_combo)

        editor_layout.addLayout(form)
        editor_layout.addStretch()

        button_row = QHBoxLayout()
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self._save)
        self.complete_button = QPushButton("完成")
        self.complete_button.clicked.connect(self._complete)
        self.restore_button = QPushButton("恢复")
        self.restore_button.clicked.connect(self._restore)
        self.delete_button = QPushButton("删除")
        self.delete_button.clicked.connect(self._delete)
        self.clear_completed_button = QPushButton("清空已完成")
        self.clear_completed_button.clicked.connect(self._clear_completed)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.complete_button)
        button_row.addWidget(self.restore_button)
        button_row.addWidget(self.delete_button)
        button_row.addStretch()
        button_row.addWidget(self.clear_completed_button)
        editor_layout.addLayout(button_row)
        self.splitter.addWidget(editor)
        self.splitter.setSizes([310, 470])

        self._sync_recurrence_controls()
        self._sync_date_controls(self.no_date_check.isChecked())
        self._rebuild_calendar_menu()

    def _make_list(self) -> QListWidget:
        widget = QListWidget()
        widget.setSelectionMode(QAbstractItemView.SingleSelection)
        widget.itemSelectionChanged.connect(self._selection_changed)
        widget.setAlternatingRowColors(True)
        return widget

    def refresh(self, restore_selection: bool = True) -> None:
        if self._refreshing:
            return
        selected_id = self._selected_occurrence_id
        self._refreshing = True
        try:
            now = local_now()
            today = now.date()
            self._fill_list(self.today_list, self.store.list_today(today, self.work_calendar), now)
            self._fill_list(self.undated_list, self.store.list_undated(), now)
            self._fill_list(
                self.planned_list,
                self.store.list_planned(today, self.work_calendar),
                now,
            )
            self._fill_list(self.completed_list, self.store.list_completed(), now)
            if restore_selection and selected_id is not None:
                if not self._restore_selection(selected_id, quiet=True):
                    self.start_new()
        finally:
            self._refreshing = False
        self._sync_editor_buttons()
        self._rebuild_calendar_menu()

    def _tab_changed(self, _index: int) -> None:
        if self._refreshing:
            return
        self.start_new()
        self.refresh(restore_selection=False)

    def start_new(self) -> None:
        self._selected_occurrence_id = None
        self._clear_list_selection()
        now = local_now()
        self.title_edit.clear()
        self.note_edit.clear()
        self.date_edit.setDate(_to_qdate(now.date()))
        self.no_date_check.setChecked(False)
        self.has_time_check.setChecked(False)
        self.time_edit.setTime(_to_qtime(None))
        self.recurrence_combo.setCurrentIndex(0)
        self.interval_spin.setValue(1)
        self.skip_holidays_check.setChecked(False)
        self.scope_combo.setCurrentIndex(0)
        self._set_editor_readonly(False)
        self._sync_editor_buttons()

    def select_occurrence(self, occurrence_id: int) -> None:
        self._selected_occurrence_id = occurrence_id
        self.refresh()
        occurrence = self.store.get_occurrence(occurrence_id)
        if occurrence is not None:
            self._load_occurrence(occurrence)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        wanted = Qt.Vertical if self.width() < 620 else Qt.Horizontal
        if self.splitter.orientation() != wanted:
            self.splitter.setOrientation(wanted)

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def _fill_list(
        self,
        widget: QListWidget,
        occurrences: list[TodoOccurrence],
        now: datetime,
    ) -> None:
        widget.clear()
        for occurrence in occurrences:
            item = QListWidgetItem(self._format_occurrence(occurrence, now))
            item.setData(Qt.UserRole, occurrence.id)
            if occurrence_is_due_at(occurrence, now):
                font = QFont(item.font())
                font.setBold(True)
                item.setFont(font)
                item.setForeground(QColor("#b42318"))
                item.setBackground(QColor("#fff1f0"))
            if occurrence.note:
                item.setToolTip(occurrence.note)
            widget.addItem(item)

    def _restore_selection(self, occurrence_id: int, quiet: bool = False) -> bool:
        for index, widget in enumerate(
            (self.today_list, self.undated_list, self.planned_list, self.completed_list)
        ):
            for row in range(widget.count()):
                item = widget.item(row)
                if item.data(Qt.UserRole) == occurrence_id:
                    tab_blocker = QSignalBlocker(self.tabs) if quiet else None
                    widget_blocker = QSignalBlocker(widget) if quiet else None
                    try:
                        self.tabs.setCurrentIndex(index)
                        widget.setCurrentItem(item)
                    finally:
                        del widget_blocker
                        del tab_blocker
                    return True
        return False

    def _clear_list_selection(self) -> None:
        for widget in (
            self.today_list,
            self.undated_list,
            self.planned_list,
            self.completed_list,
        ):
            blocker = QSignalBlocker(widget)
            try:
                widget.clearSelection()
                widget.setCurrentRow(-1)
            finally:
                del blocker

    def _selection_changed(self) -> None:
        if self._refreshing:
            return
        item = self.sender().currentItem()
        if item is None:
            return
        occurrence_id = item.data(Qt.UserRole)
        occurrence = self.store.get_occurrence(int(occurrence_id))
        if occurrence is not None:
            self._load_occurrence(occurrence)

    def _load_occurrence(self, occurrence: TodoOccurrence) -> None:
        self._selected_occurrence_id = occurrence.id
        self.title_edit.setText(occurrence.title)
        self.note_edit.setPlainText(occurrence.note)
        self.no_date_check.setChecked(occurrence.due_date is None)
        self.date_edit.setDate(_to_qdate(occurrence.due_date or local_now().date()))
        self.has_time_check.setChecked(occurrence.due_time is not None)
        self.time_edit.setTime(_to_qtime(occurrence.due_time))
        self._set_recurrence(occurrence.recurrence)
        self.interval_spin.setValue(max(1, occurrence.interval_days))
        self.skip_holidays_check.setChecked(occurrence.skip_holidays)
        self.scope_combo.setCurrentIndex(0)
        self._set_editor_readonly(occurrence.status == STATUS_COMPLETED)
        self._sync_editor_buttons()

    def _format_occurrence(self, occurrence: TodoOccurrence, now: datetime) -> str:
        today = now.date()
        time_text = time_to_text(occurrence.due_time)
        if occurrence.due_date is None:
            return f"无日期  {occurrence.title}"
        if occurrence.status == STATUS_COMPLETED:
            prefix = f"{occurrence.due_date.isoformat()} {time_text or '全天'}"
            return f"{prefix}  {occurrence.title}"
        if occurrence_is_due_at(occurrence, now):
            if occurrence.due_date < today:
                prefix = f"🔔 逾期 {occurrence.due_date.isoformat()} {time_text or '全天'}"
            elif occurrence.due_time is None:
                prefix = "🔔 今天"
            else:
                prefix = f"🔔 已到 {time_text}"
        elif occurrence.due_date < today:
            prefix = f"逾期 {occurrence.due_date.isoformat()} {time_text or '全天'}"
        elif occurrence.due_date == today:
            prefix = time_text or "今天"
        else:
            prefix = f"{occurrence.due_date.isoformat()} {time_text or '全天'}"
        return f"{prefix}  {occurrence.title}"

    def _set_recurrence(self, recurrence: str) -> None:
        for index in range(self.recurrence_combo.count()):
            if self.recurrence_combo.itemData(index) == recurrence:
                self.recurrence_combo.setCurrentIndex(index)
                return
        self.recurrence_combo.setCurrentIndex(0)

    def _sync_time_enabled(self, enabled: bool) -> None:
        date_controls_enabled = (
            self.title_edit.isEnabled() and not self.no_date_check.isChecked()
        )
        self.has_time_check.setEnabled(date_controls_enabled)
        self.time_edit.setEnabled(enabled and date_controls_enabled)

    def _sync_date_controls(self, undated: bool) -> None:
        if undated:
            self.has_time_check.setChecked(False)
            self._set_recurrence(RECURRENCE_NONE)
            self.skip_holidays_check.setChecked(False)
        self.date_edit.setEnabled(self.title_edit.isEnabled() and not undated)
        self._sync_time_enabled(self.has_time_check.isChecked())
        self._sync_recurrence_controls()
        self._sync_calendar_limits()

    def _sync_recurrence_controls(self) -> None:
        recurrence = self.recurrence_combo.currentData()
        self.interval_spin.setVisible(recurrence == RECURRENCE_EVERY_N_DAYS)
        self._sync_scope_controls()

    def _sync_scope_controls(self) -> None:
        occurrence = (
            self.store.get_occurrence(self._selected_occurrence_id)
            if self._selected_occurrence_id is not None
            else None
        )
        is_recurring = bool(occurrence and occurrence.is_recurring)
        self.scope_combo.setVisible(is_recurring and occurrence.status != STATUS_COMPLETED)
        single = self.scope_combo.currentData() == "single"
        if is_recurring and single and self.no_date_check.isChecked():
            self.no_date_check.setChecked(False)
        editor_enabled = self.title_edit.isEnabled()
        undated = self.no_date_check.isChecked()
        self.no_date_check.setEnabled(editor_enabled and not (is_recurring and single))
        recurrence_enabled = not single and editor_enabled and not undated
        self.recurrence_combo.setEnabled(recurrence_enabled)
        self.interval_spin.setEnabled(recurrence_enabled)
        self.skip_holidays_check.setEnabled(recurrence_enabled)

    def _sync_calendar_limits(self) -> None:
        if self.skip_holidays_check.isChecked() and self.work_calendar.covered_end:
            self.date_edit.setMaximumDate(_to_qdate(self.work_calendar.covered_end))
            if self.work_calendar.covered_start:
                self.date_edit.setMinimumDate(_to_qdate(self.work_calendar.covered_start))
        else:
            self.date_edit.setMinimumDate(QDate(2000, 1, 1))
            self.date_edit.setMaximumDate(QDate(9999, 12, 31))

    def _sync_editor_buttons(self) -> None:
        occurrence = (
            self.store.get_occurrence(self._selected_occurrence_id)
            if self._selected_occurrence_id is not None
            else None
        )
        is_completed = bool(occurrence and occurrence.status == STATUS_COMPLETED)
        has_selection = occurrence is not None
        self.save_button.setVisible(not is_completed)
        self.complete_button.setVisible(has_selection and not is_completed)
        self.restore_button.setVisible(is_completed)
        self.delete_button.setVisible(has_selection)
        self.clear_completed_button.setVisible(self.tabs.currentWidget() == self.completed_list)
        self._sync_recurrence_controls()
        self._sync_calendar_limits()

    def _set_editor_readonly(self, readonly: bool) -> None:
        enabled = not readonly
        for widget in (
            self.title_edit,
            self.note_edit,
            self.date_edit,
            self.no_date_check,
            self.has_time_check,
            self.time_edit,
            self.recurrence_combo,
            self.interval_spin,
            self.skip_holidays_check,
            self.scope_combo,
        ):
            widget.setEnabled(enabled)
        self._sync_date_controls(self.no_date_check.isChecked())

    def _form_values(self):
        title = self.title_edit.text().strip()
        note = self.note_edit.toPlainText()
        undated = self.no_date_check.isChecked()
        due_date = None if undated else _from_qdate(self.date_edit.date())
        due_time = None
        if not undated and self.has_time_check.isChecked():
            due_time = snap_time_to_step(_from_qtime(self.time_edit.time()))
        if due_time is not None:
            self.time_edit.setTime(QTime(due_time.hour, due_time.minute))
        recurrence = RECURRENCE_NONE if undated else self.recurrence_combo.currentData()
        interval_days = 1 if undated else self.interval_spin.value()
        skip_holidays = False if undated else self.skip_holidays_check.isChecked()
        return title, note, due_date, due_time, recurrence, interval_days, skip_holidays

    def _validate_new_due_time(
        self,
        due_date: Optional[date],
        due_time: Optional[time],
    ) -> None:
        if self._selected_occurrence_id is not None:
            return
        if due_date is None:
            return
        now = local_now()
        if due_date < now.date():
            raise TodoValidationError("新待办不能选择过去日期")
        if due_date == now.date() and due_time is not None:
            current_minute = time(now.hour, now.minute)
            if due_time < current_minute:
                raise TodoValidationError("今天的新待办不能选择已过去的时间")

    def _save(self) -> None:
        try:
            title, note, due_date, due_time, recurrence, interval_days, skip_holidays = (
                self._form_values()
            )
            self._validate_new_due_time(due_date, due_time)
            if self._selected_occurrence_id is None:
                self.store.add_todo(
                    title,
                    note,
                    due_date,
                    due_time,
                    recurrence,
                    interval_days,
                    skip_holidays,
                    self.work_calendar,
                )
                self.start_new()
            else:
                occurrence = self.store.get_occurrence(self._selected_occurrence_id)
                if occurrence is None:
                    return
                if occurrence.is_recurring and self.scope_combo.currentData() == "single":
                    self.store.update_occurrence_only(
                        occurrence.id,
                        title,
                        note,
                        due_date,
                        due_time,
                    )
                else:
                    self.store.update_current_and_future(
                        occurrence.id,
                        title,
                        note,
                        due_date,
                        due_time,
                        recurrence,
                        interval_days,
                        skip_holidays,
                        self.work_calendar,
                    )
            self.refresh()
            self.todos_changed.emit()
        except TodoValidationError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))

    def _complete(self) -> None:
        if self._selected_occurrence_id is None:
            return
        self.store.complete_occurrence(self._selected_occurrence_id)
        self.refresh()
        self.todos_changed.emit()

    def _restore(self) -> None:
        if self._selected_occurrence_id is None:
            return
        self.store.restore_occurrence(self._selected_occurrence_id)
        self.refresh()
        self.todos_changed.emit()

    def _delete(self) -> None:
        if self._selected_occurrence_id is None:
            return
        occurrence = self.store.get_occurrence(self._selected_occurrence_id)
        if occurrence is None:
            return
        if occurrence.is_recurring and occurrence.status != STATUS_COMPLETED:
            box = QMessageBox(self)
            box.setWindowTitle("删除重复待办")
            box.setText("要删除本次，还是整个重复待办？")
            current_button = box.addButton("删除本次", QMessageBox.AcceptRole)
            series_button = box.addButton("删除整个系列", QMessageBox.DestructiveRole)
            box.addButton("取消", QMessageBox.RejectRole)
            box.exec_()
            clicked = box.clickedButton()
            if clicked == current_button:
                self.store.delete_occurrence_only(occurrence.id)
            elif clicked == series_button:
                self.store.delete_series_from_occurrence(occurrence.id)
            else:
                return
        else:
            reply = QMessageBox.question(
                self,
                "删除待办",
                "确认删除这个待办？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self.store.delete_occurrence_only(occurrence.id)
        self._selected_occurrence_id = None
        self.refresh()
        self.todos_changed.emit()

    def _clear_completed(self) -> None:
        reply = QMessageBox.question(
            self,
            "清空已完成",
            "确认清空所有已完成记录？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.store.clear_completed()
        self._selected_occurrence_id = None
        self.refresh()
        self.todos_changed.emit()

    def _rebuild_calendar_menu(self) -> None:
        self.calendar_menu.clear()
        status_action = self.calendar_menu.addAction(self.work_calendar.status_text())
        status_action.setEnabled(False)
        if self.work_calendar.load_error:
            error_action = self.calendar_menu.addAction(self.work_calendar.load_error)
            error_action.setEnabled(False)
        self.calendar_menu.addSeparator()
        update_action = self.calendar_menu.addAction("在线检查更新")
        update_action.triggered.connect(self._check_calendar_update)

    def _check_calendar_update(self) -> None:
        self.calendar_button.setEnabled(False)
        if self._network_manager is None:
            self._network_manager = QNetworkAccessManager(self)
            self._network_manager.finished.connect(self._calendar_download_finished)
        self._pending_calendar_urls = list(self.work_calendar.update_urls)
        self._calendar_update_errors = []
        self._download_next_calendar_url()

    def _download_next_calendar_url(self) -> None:
        if not self._pending_calendar_urls:
            self.calendar_button.setEnabled(True)
            detail = "\n".join(self._calendar_update_errors) or "没有可用下载地址"
            if calendar_errors_are_not_found(self._calendar_update_errors):
                QMessageBox.information(
                    self,
                    "在线日历尚未发布",
                    "远端仓库还没有发布日历 JSON，当前继续使用已有日历。\n\n"
                    f"{detail}",
                )
            else:
                QMessageBox.warning(
                    self,
                    "日历更新失败",
                    f"在线日历更新失败，已保留当前本地日历。\n\n{detail}",
                )
            return
        self._current_calendar_update_url = self._pending_calendar_urls.pop(0)
        request = QNetworkRequest(QUrl(self._current_calendar_update_url))
        request.setRawHeader(b"User-Agent", b"DesktopPet")
        if hasattr(QNetworkRequest, "FollowRedirectsAttribute"):
            request.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        self._network_manager.get(request)

    def _calendar_download_finished(self, reply) -> None:
        try:
            if reply.error():
                self._calendar_update_errors.append(
                    f"{self._current_calendar_update_url}: {reply.errorString()}"
                )
                self._download_next_calendar_url()
                return
            payload = bytes(reply.readAll())
            save_user_calendar(payload, self.work_calendar.user_path)
            self.work_calendar.reload()
            self.store.materialize(local_now().date(), self.work_calendar)
            self.refresh()
            self.calendar_changed.emit()
            QMessageBox.information(self, "日历已更新", self.work_calendar.status_text())
            self.calendar_button.setEnabled(True)
        except (CalendarDataError, OSError) as exc:
            self._calendar_update_errors.append(
                f"{self._current_calendar_update_url}: {exc}"
            )
            self._download_next_calendar_url()
        finally:
            reply.deleteLater()

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
