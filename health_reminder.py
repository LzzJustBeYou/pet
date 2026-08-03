"""健康提醒控制器（Eye Monitor / Stretchly 风格）。

默认采用 20-20-20 规则：每工作 20 分钟休息 20 秒（看远处）；
每完成 N 次短休息后进入一次长休息（默认 4 次后休息 5 分钟）。
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class HealthReminderController(QObject):
    break_started = pyqtSignal(str, int)  # (kind, seconds): "micro" | "long"
    break_ticked = pyqtSignal(int)        # 剩余秒数
    break_finished = pyqtSignal(str)
    break_skipped = pyqtSignal(str)

    def __init__(
        self,
        parent: Optional[QObject] = None,
        work_minutes: int = 20,
        break_seconds: int = 20,
        long_break_every: int = 4,
        long_break_minutes: int = 5,
        enabled: bool = True,
    ):
        super().__init__(parent)
        self.work_minutes = max(1, int(work_minutes))
        self.break_seconds = max(5, int(break_seconds))
        self.long_break_every = max(2, int(long_break_every))
        self.long_break_minutes = max(1, int(long_break_minutes))
        self._enabled = bool(enabled)
        self._paused = False
        self._completed_breaks = 0
        self._break_kind = "micro"
        self._countdown_remaining = 0

        self._work_timer = QTimer(self)
        self._work_timer.setSingleShot(True)
        self._work_timer.timeout.connect(self._start_break)

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def active(self) -> bool:
        return self._countdown_timer.isActive()

    @property
    def remaining(self) -> int:
        return self._countdown_remaining

    # ------------------------------------------------------------------
    # 控制
    # ------------------------------------------------------------------

    def start(self) -> None:
        """按当前配置开始工作计时（幂等）。"""
        self._schedule_work()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if self._enabled:
            self._schedule_work()
        else:
            self._work_timer.stop()

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)
        if self._paused:
            self._work_timer.stop()
        else:
            self._schedule_work()

    def apply_config(
        self,
        work_minutes: Optional[int] = None,
        break_seconds: Optional[int] = None,
        long_break_every: Optional[int] = None,
        long_break_minutes: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        if work_minutes is not None:
            self.work_minutes = max(1, int(work_minutes))
        if break_seconds is not None:
            self.break_seconds = max(5, int(break_seconds))
        if long_break_every is not None:
            self.long_break_every = max(2, int(long_break_every))
        if long_break_minutes is not None:
            self.long_break_minutes = max(1, int(long_break_minutes))
        if enabled is not None:
            self._enabled = bool(enabled)
        # 休息进行中不打断，结束后按新配置排程
        if not self.active:
            self._schedule_work()

    def start_break_now(self) -> None:
        self._work_timer.stop()
        self._start_break()

    def skip_break(self) -> None:
        if not self.active:
            return
        self._countdown_timer.stop()
        kind = self._break_kind
        self.break_skipped.emit(kind)
        self._schedule_work()

    def stop_all(self) -> None:
        self._work_timer.stop()
        self._countdown_timer.stop()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _schedule_work(self) -> None:
        self._work_timer.stop()
        if self._enabled and not self._paused:
            self._work_timer.start(self.work_minutes * 60 * 1000)

    def _start_break(self) -> None:
        if not self._enabled or self._paused:
            return
        next_number = self._completed_breaks + 1
        long_break = next_number % self.long_break_every == 0
        self._break_kind = "long" if long_break else "micro"
        self._countdown_remaining = (
            self.long_break_minutes * 60
            if long_break
            else self.break_seconds
        )
        self.break_started.emit(self._break_kind, self._countdown_remaining)
        self._countdown_timer.start()

    def _tick(self) -> None:
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._finish_break()
        else:
            self.break_ticked.emit(self._countdown_remaining)

    def _finish_break(self) -> None:
        self._countdown_timer.stop()
        kind = self._break_kind
        if kind == "micro":
            self._completed_breaks += 1
        else:
            self._completed_breaks = 0
        self.break_finished.emit(kind)
        self._schedule_work()
