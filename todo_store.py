from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable, Optional

try:
    from PyQt5.QtCore import QStandardPaths
except ImportError:  # pragma: no cover - exercised only when PyQt5 is absent.
    QStandardPaths = None

from holiday_calendar import HolidayCalendar
from todo_models import (
    RECURRENCE_EVERY_N_DAYS,
    RECURRENCE_NONE,
    STATUS_COMPLETED,
    STATUS_DELETED,
    STATUS_PENDING,
    TodoOccurrence,
    TodoSeries,
    date_to_text,
    datetime_to_text,
    local_now,
    normalize_recurrence,
    optional_date_to_text,
    text_to_datetime,
    text_to_optional_date,
    text_to_time,
    time_to_text,
)
from todo_recurrence import occurrence_dates_until


class TodoValidationError(ValueError):
    pass


def default_database_path() -> Path:
    if QStandardPaths is not None:
        location = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        if location:
            return Path(location) / "todo.sqlite3"
    return Path.home() / ".desktop_pet" / "todo.sqlite3"


class TodoStore:
    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path is not None else default_database_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=3.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 3000")
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS todo_series (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    start_date TEXT NOT NULL,
                    due_time TEXT NOT NULL DEFAULT '',
                    recurrence TEXT NOT NULL DEFAULT 'none',
                    interval_days INTEGER NOT NULL DEFAULT 1,
                    skip_holidays INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );

                CREATE TABLE IF NOT EXISTS todo_occurrences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    series_id INTEGER NOT NULL REFERENCES todo_series(id),
                    title TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    due_date TEXT NOT NULL,
                    due_time TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    completed_at TEXT,
                    notified_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_override INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(series_id, due_date, due_time)
                );

                CREATE INDEX IF NOT EXISTS idx_todo_occ_due
                    ON todo_occurrences(status, due_date, due_time);
                CREATE INDEX IF NOT EXISTS idx_todo_occ_completed
                    ON todo_occurrences(status, completed_at);
                CREATE INDEX IF NOT EXISTS idx_todo_occ_notify
                    ON todo_occurrences(status, notified_at, due_date, due_time);
                """
            )
            conn.commit()

    def add_todo(
        self,
        title: str,
        note: str,
        due_date: Optional[date],
        due_time: Optional[time],
        recurrence: str = RECURRENCE_NONE,
        interval_days: int = 1,
        skip_holidays: bool = False,
        work_calendar: Optional[HolidayCalendar] = None,
    ) -> int:
        title = title.strip()
        if not title:
            raise TodoValidationError("标题不能为空")
        recurrence = normalize_recurrence(recurrence)
        interval_days = self._normalize_interval(recurrence, interval_days)
        if due_date is None:
            if recurrence != RECURRENCE_NONE:
                raise TodoValidationError("无日期待办不能设置重复")
            if due_time is not None:
                raise TodoValidationError("无日期待办不能设置时间")
            if skip_holidays:
                raise TodoValidationError("无日期待办不能跳过节假日")
        if skip_holidays and due_date is not None:
            calendar = work_calendar or HolidayCalendar()
            if not calendar.is_covered(due_date):
                raise TodoValidationError("跳过节假日的任务日期必须在已加载日历范围内")

        now_text = datetime_to_text(local_now())
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO todo_series (
                    title, note, start_date, due_time, recurrence,
                    interval_days, skip_holidays, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    note or "",
                    optional_date_to_text(due_date),
                    time_to_text(due_time) or "",
                    recurrence,
                    interval_days,
                    1 if skip_holidays else 0,
                    now_text,
                    now_text,
                ),
            )
            series_id = int(cursor.lastrowid)
            series = self._get_series_in_conn(conn, series_id)
            if series is not None:
                self._materialize_series_in_conn(
                    conn,
                    series,
                    local_now().date(),
                    work_calendar or HolidayCalendar(),
                    resurrect=False,
                )
            conn.commit()
            return series_id

    def materialize(
        self,
        through_date: date,
        work_calendar: Optional[HolidayCalendar] = None,
    ) -> None:
        calendar = work_calendar or HolidayCalendar()
        with self._connect() as conn:
            for series in self._iter_active_series_in_conn(conn):
                self._materialize_series_in_conn(conn, series, through_date, calendar)
            conn.commit()

    def list_today(
        self,
        today: date,
        work_calendar: Optional[HolidayCalendar] = None,
    ) -> list[TodoOccurrence]:
        self.materialize(today, work_calendar)
        with self._connect() as conn:
            rows = conn.execute(
                self._occurrence_select()
                + """
                WHERE o.status = ? AND o.due_date <> '' AND o.due_date <= ?
                ORDER BY o.due_date ASC, o.due_time ASC
                """,
                (STATUS_PENDING, date_to_text(today)),
            ).fetchall()
        occurrences = [self._occurrence_from_row(row) for row in rows]
        return sorted(occurrences, key=lambda item: self._today_sort_key(item, today))

    def list_planned(
        self,
        today: date,
        work_calendar: Optional[HolidayCalendar] = None,
    ) -> list[TodoOccurrence]:
        self.materialize(today, work_calendar)
        with self._connect() as conn:
            rows = conn.execute(
                self._occurrence_select()
                + """
                WHERE o.status = ? AND o.due_date <> '' AND o.due_date > ?
                ORDER BY o.due_date ASC, o.due_time ASC
                """,
                (STATUS_PENDING, date_to_text(today)),
            ).fetchall()
        return [self._occurrence_from_row(row) for row in rows]

    def list_undated(self) -> list[TodoOccurrence]:
        with self._connect() as conn:
            rows = conn.execute(
                self._occurrence_select()
                + """
                WHERE o.status = ? AND o.due_date = ''
                ORDER BY o.created_at DESC, o.id DESC
                """,
                (STATUS_PENDING,),
            ).fetchall()
        return [self._occurrence_from_row(row) for row in rows]

    def list_completed(self, limit: int = 500) -> list[TodoOccurrence]:
        with self._connect() as conn:
            rows = conn.execute(
                self._occurrence_select()
                + """
                WHERE o.status = ?
                ORDER BY o.completed_at DESC, o.due_date DESC, o.due_time DESC
                LIMIT ?
                """,
                (STATUS_COMPLETED, limit),
            ).fetchall()
        return [self._occurrence_from_row(row) for row in rows]

    def badge_count(
        self,
        today: date,
        work_calendar: Optional[HolidayCalendar] = None,
    ) -> int:
        self.materialize(today, work_calendar)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM todo_occurrences
                WHERE status = ? AND due_date <> '' AND due_date <= ?
                """,
                (STATUS_PENDING, date_to_text(today)),
            ).fetchone()
        return int(row["count"] if row else 0)

    def reminder_count(
        self,
        now: datetime,
        work_calendar: Optional[HolidayCalendar] = None,
    ) -> int:
        self.materialize(now.date(), work_calendar)
        now_date = date_to_text(now.date())
        now_time = now.strftime("%H:%M")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM todo_occurrences
                WHERE status = ?
                  AND due_date <> ''
                  AND (
                    due_date < ?
                    OR (
                        due_date = ?
                        AND (due_time = '' OR due_time <= ?)
                    )
                  )
                """,
                (STATUS_PENDING, now_date, now_date, now_time),
            ).fetchone()
        return int(row["count"] if row else 0)

    def get_occurrence(self, occurrence_id: int) -> Optional[TodoOccurrence]:
        with self._connect() as conn:
            row = conn.execute(
                self._occurrence_select() + "WHERE o.id = ?",
                (occurrence_id,),
            ).fetchone()
        return self._occurrence_from_row(row) if row else None

    def complete_occurrence(self, occurrence_id: int) -> None:
        now_text = datetime_to_text(local_now())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE todo_occurrences
                SET status = ?, completed_at = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (STATUS_COMPLETED, now_text, now_text, occurrence_id, STATUS_PENDING),
            )
            conn.commit()

    def restore_occurrence(self, occurrence_id: int) -> None:
        now_text = datetime_to_text(local_now())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE todo_occurrences
                SET status = ?, completed_at = NULL, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (STATUS_PENDING, now_text, occurrence_id, STATUS_COMPLETED),
            )
            conn.commit()

    def delete_occurrence_only(self, occurrence_id: int) -> None:
        now_text = datetime_to_text(local_now())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE todo_occurrences
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (STATUS_DELETED, now_text, occurrence_id),
            )
            conn.commit()

    def delete_series_from_occurrence(self, occurrence_id: int) -> None:
        now_text = datetime_to_text(local_now())
        with self._connect() as conn:
            occurrence = conn.execute(
                "SELECT series_id FROM todo_occurrences WHERE id = ?",
                (occurrence_id,),
            ).fetchone()
            if occurrence is None:
                return
            series_id = int(occurrence["series_id"])
            conn.execute(
                """
                UPDATE todo_series
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (now_text, now_text, series_id),
            )
            conn.execute(
                """
                UPDATE todo_occurrences
                SET status = ?, updated_at = ?
                WHERE series_id = ? AND status = ?
                """,
                (STATUS_DELETED, now_text, series_id, STATUS_PENDING),
            )
            conn.commit()

    def clear_completed(self) -> None:
        now_text = datetime_to_text(local_now())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE todo_occurrences
                SET status = ?, updated_at = ?
                WHERE status = ?
                """,
                (STATUS_DELETED, now_text, STATUS_COMPLETED),
            )
            conn.commit()

    def update_occurrence_only(
        self,
        occurrence_id: int,
        title: str,
        note: str,
        due_date: Optional[date],
        due_time: Optional[time],
    ) -> None:
        title = title.strip()
        if not title:
            raise TodoValidationError("标题不能为空")
        if due_date is None and due_time is not None:
            raise TodoValidationError("无日期待办不能设置时间")
        now_text = datetime_to_text(local_now())
        try:
            with self._connect() as conn:
                current = conn.execute(
                    """
                    SELECT s.recurrence AS recurrence
                    FROM todo_occurrences o
                    JOIN todo_series s ON s.id = o.series_id
                    WHERE o.id = ?
                    """,
                    (occurrence_id,),
                ).fetchone()
                if current is None:
                    return
                if (
                    due_date is None
                    and normalize_recurrence(str(current["recurrence"])) != RECURRENCE_NONE
                ):
                    raise TodoValidationError("重复待办不能设置为无日期")
                conn.execute(
                    """
                    UPDATE todo_occurrences
                    SET title = ?, note = ?, due_date = ?, due_time = ?,
                        updated_at = ?, is_override = 1
                    WHERE id = ?
                    """,
                    (
                        title,
                        note or "",
                        optional_date_to_text(due_date),
                        time_to_text(due_time) or "",
                        now_text,
                        occurrence_id,
                    ),
                )
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise TodoValidationError("同一重复待办里已经有这个日期时间") from exc

    def update_current_and_future(
        self,
        occurrence_id: int,
        title: str,
        note: str,
        due_date: Optional[date],
        due_time: Optional[time],
        recurrence: str,
        interval_days: int,
        skip_holidays: bool,
        work_calendar: Optional[HolidayCalendar] = None,
    ) -> None:
        title = title.strip()
        if not title:
            raise TodoValidationError("标题不能为空")
        recurrence = normalize_recurrence(recurrence)
        interval_days = self._normalize_interval(recurrence, interval_days)
        if due_date is None:
            if recurrence != RECURRENCE_NONE:
                raise TodoValidationError("无日期待办不能设置重复")
            if due_time is not None:
                raise TodoValidationError("无日期待办不能设置时间")
            if skip_holidays:
                raise TodoValidationError("无日期待办不能跳过节假日")
        if skip_holidays and due_date is not None:
            calendar = work_calendar or HolidayCalendar()
            if not calendar.is_covered(due_date):
                raise TodoValidationError("跳过节假日的任务日期必须在已加载日历范围内")

        now_text = datetime_to_text(local_now())
        with self._connect() as conn:
            current = conn.execute(
                "SELECT series_id, due_date, due_time FROM todo_occurrences WHERE id = ?",
                (occurrence_id,),
            ).fetchone()
            if current is None:
                return
            series_id = int(current["series_id"])
            selected_date = current["due_date"]
            selected_time = current["due_time"]
            conn.execute(
                """
                UPDATE todo_series
                SET title = ?, note = ?, start_date = ?, due_time = ?,
                    recurrence = ?, interval_days = ?, skip_holidays = ?,
                    updated_at = ?, deleted_at = NULL
                WHERE id = ?
                """,
                (
                    title,
                    note or "",
                    optional_date_to_text(due_date),
                    time_to_text(due_time) or "",
                    recurrence,
                    interval_days,
                    1 if skip_holidays else 0,
                    now_text,
                    series_id,
                ),
            )
            conn.execute(
                """
                UPDATE todo_occurrences
                SET status = ?, updated_at = ?
                WHERE series_id = ? AND status = ?
                  AND (
                    due_date > ?
                    OR (due_date = ? AND due_time >= ?)
                  )
                """,
                (
                    STATUS_DELETED,
                    now_text,
                    series_id,
                    STATUS_PENDING,
                    selected_date,
                    selected_date,
                    selected_time,
                ),
            )
            series = self._get_series_in_conn(conn, series_id)
            if series is not None:
                self._materialize_series_in_conn(
                    conn,
                    series,
                    local_now().date(),
                    work_calendar or HolidayCalendar(),
                    resurrect=True,
                )
            conn.commit()

    def claim_due_reminders(
        self,
        now: datetime,
        work_calendar: Optional[HolidayCalendar] = None,
        limit: int = 10,
    ) -> list[TodoOccurrence]:
        self.materialize(now.date(), work_calendar)
        now_date = date_to_text(now.date())
        now_time = now.strftime("%H:%M")
        now_text = datetime_to_text(now)
        claimed: list[TodoOccurrence] = []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM todo_occurrences
                WHERE status = ?
                  AND due_date <> ''
                  AND due_time <> ''
                  AND notified_at IS NULL
                  AND (
                    due_date < ?
                    OR (due_date = ? AND due_time <= ?)
                  )
                ORDER BY due_date ASC, due_time ASC
                LIMIT ?
                """,
                (STATUS_PENDING, now_date, now_date, now_time, limit),
            ).fetchall()
            for row in rows:
                cursor = conn.execute(
                    """
                    UPDATE todo_occurrences
                    SET notified_at = ?, updated_at = ?
                    WHERE id = ? AND notified_at IS NULL AND status = ?
                    """,
                    (now_text, now_text, int(row["id"]), STATUS_PENDING),
                )
                if cursor.rowcount != 1:
                    continue
                occurrence = conn.execute(
                    self._occurrence_select() + "WHERE o.id = ?",
                    (int(row["id"]),),
                ).fetchone()
                if occurrence is not None:
                    claimed.append(self._occurrence_from_row(occurrence))
            conn.commit()
        return claimed

    def _normalize_interval(self, recurrence: str, interval_days: int) -> int:
        if recurrence != RECURRENCE_EVERY_N_DAYS:
            return 1
        try:
            value = int(interval_days)
        except (TypeError, ValueError):
            value = 1
        if value < 1 or value > 365:
            raise TodoValidationError("每 N 天的 N 必须在 1 到 365 之间")
        return value

    def _materialize_series_in_conn(
        self,
        conn: sqlite3.Connection,
        series: TodoSeries,
        through_date: date,
        work_calendar: HolidayCalendar,
        resurrect: bool = False,
    ) -> None:
        if series.start_date is None:
            self._insert_occurrence_in_conn(conn, series, None, resurrect=resurrect)
            return
        for due_date in occurrence_dates_until(series, through_date, work_calendar):
            self._insert_occurrence_in_conn(conn, series, due_date, resurrect=resurrect)

    def _insert_occurrence_in_conn(
        self,
        conn: sqlite3.Connection,
        series: TodoSeries,
        due_date: Optional[date],
        resurrect: bool = False,
    ) -> None:
        now_text = datetime_to_text(local_now())
        due_time = time_to_text(series.due_time) or ""
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO todo_occurrences (
                series_id, title, note, due_date, due_time, status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                series.id,
                series.title,
                series.note,
                optional_date_to_text(due_date),
                due_time,
                STATUS_PENDING,
                now_text,
                now_text,
            ),
        )
        if resurrect and cursor.rowcount == 0:
            conn.execute(
                """
                UPDATE todo_occurrences
                SET title = ?, note = ?, due_date = ?, due_time = ?,
                    status = ?, completed_at = NULL, notified_at = NULL,
                    updated_at = ?, is_override = 0
                WHERE series_id = ? AND due_date = ? AND due_time = ?
                  AND status = ?
                """,
                (
                    series.title,
                    series.note,
                    optional_date_to_text(due_date),
                    due_time,
                    STATUS_PENDING,
                    now_text,
                    series.id,
                    optional_date_to_text(due_date),
                    due_time,
                    STATUS_DELETED,
                ),
            )

    def _iter_active_series_in_conn(self, conn: sqlite3.Connection) -> Iterable[TodoSeries]:
        rows = conn.execute(
            """
            SELECT *
            FROM todo_series
            WHERE deleted_at IS NULL
            ORDER BY id ASC
            """
        ).fetchall()
        for row in rows:
            yield self._series_from_row(row)

    def _get_series_in_conn(
        self,
        conn: sqlite3.Connection,
        series_id: int,
    ) -> Optional[TodoSeries]:
        row = conn.execute("SELECT * FROM todo_series WHERE id = ?", (series_id,)).fetchone()
        return self._series_from_row(row) if row else None

    def _series_from_row(self, row: sqlite3.Row) -> TodoSeries:
        return TodoSeries(
            id=int(row["id"]),
            title=str(row["title"]),
            note=str(row["note"] or ""),
            start_date=text_to_optional_date(row["start_date"]),
            due_time=text_to_time(row["due_time"]),
            recurrence=normalize_recurrence(str(row["recurrence"])),
            interval_days=int(row["interval_days"] or 1),
            skip_holidays=bool(row["skip_holidays"]),
            created_at=text_to_datetime(row["created_at"]) or local_now(),
            updated_at=text_to_datetime(row["updated_at"]) or local_now(),
            deleted_at=text_to_datetime(row["deleted_at"]),
        )

    def _occurrence_from_row(self, row: sqlite3.Row) -> TodoOccurrence:
        return TodoOccurrence(
            id=int(row["id"]),
            series_id=int(row["series_id"]),
            title=str(row["title"]),
            note=str(row["note"] or ""),
            due_date=text_to_optional_date(row["due_date"]),
            due_time=text_to_time(row["due_time"]),
            status=str(row["status"]),
            completed_at=text_to_datetime(row["completed_at"]),
            notified_at=text_to_datetime(row["notified_at"]),
            created_at=text_to_datetime(row["created_at"]) or local_now(),
            updated_at=text_to_datetime(row["updated_at"]) or local_now(),
            is_override=bool(row["is_override"]),
            recurrence=normalize_recurrence(str(row["recurrence"])),
            interval_days=int(row["interval_days"] or 1),
            skip_holidays=bool(row["skip_holidays"]),
            series_deleted_at=text_to_datetime(row["series_deleted_at"]),
        )

    def _occurrence_select(self) -> str:
        return """
            SELECT
                o.id AS id,
                o.series_id AS series_id,
                o.title AS title,
                o.note AS note,
                o.due_date AS due_date,
                o.due_time AS due_time,
                o.status AS status,
                o.completed_at AS completed_at,
                o.notified_at AS notified_at,
                o.created_at AS created_at,
                o.updated_at AS updated_at,
                o.is_override AS is_override,
                s.recurrence AS recurrence,
                s.interval_days AS interval_days,
                s.skip_holidays AS skip_holidays,
                s.deleted_at AS series_deleted_at
            FROM todo_occurrences o
            JOIN todo_series s ON s.id = o.series_id
            """

    def _today_sort_key(self, occurrence: TodoOccurrence, today: date) -> tuple:
        if occurrence.due_date is None:
            group = 3
        elif occurrence.due_date < today:
            group = 0
        elif occurrence.due_time is not None:
            group = 1
        else:
            group = 2
        return (
            group,
            optional_date_to_text(occurrence.due_date),
            time_to_text(occurrence.due_time) or "99:99",
            occurrence.id,
        )
