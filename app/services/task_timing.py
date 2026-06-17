"""Общая логика сроков: опоздание в днях, подписи для UI и писем."""
from datetime import datetime

NO_DEADLINE_YEAR = 2099


def safe_deadline(task):
    if not task or not task.deadline:
        return None
    if task.deadline.year >= NO_DEADLINE_YEAR:
        return None
    return task.deadline


def days_word(n):
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return "дней"
    rem = n % 10
    if rem == 1:
        return "день"
    if rem in (2, 3, 4):
        return "дня"
    return "дней"


def format_late_label(days):
    if days is None or days <= 0:
        return None
    return f"на {days} {days_word(days)}"


def compute_late_days(timing_status, deadline, report_date=None, now=None):
    """Дней просрочки (открытая задача) или опоздания при сдаче отчёта."""
    if not deadline:
        return None
    now = now or datetime.now()
    deadline_d = deadline.date() if hasattr(deadline, "date") else deadline

    if timing_status == "overdue_open":
        days = (now.date() - deadline_d).days
        return days if days > 0 else None

    if timing_status == "done_late" and report_date:
        report_d = report_date.date() if hasattr(report_date, "date") else report_date
        days = (report_d - deadline_d).days
        return days if days > 0 else None

    return None


def overdue_days_from_deadline(deadline, now=None):
    """Сколько дней прошло после срока (для открытых просроченных)."""
    if not deadline:
        return 0
    now = now or datetime.now()
    deadline_d = deadline.date() if hasattr(deadline, "date") else deadline
    return max(0, (now.date() - deadline_d).days)
