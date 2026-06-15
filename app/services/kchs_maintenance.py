"""Обслуживание данных КЧС (очистка базы и т.п.)."""
from models import (
    db,
    Task,
    Executor,
    FileDocument,
    YandexReport,
    YandexReportTaskLink,
    TaskNotificationLog,
    Report,
)


def kchs_data_counts():
    return {
        "notification_logs": TaskNotificationLog.query.count(),
        "yandex_links": YandexReportTaskLink.query.count(),
        "yandex_reports": YandexReport.query.count(),
        "tasks": Task.query.count(),
        "documents": FileDocument.query.count(),
        "reports": Report.query.count(),
        "executors": Executor.query.count(),
    }


def clear_kchs_database():
    """Удалить все поручения, протоколы и отчёты с диска. Настройки уведомлений сохраняются."""
    before = kchs_data_counts()

    TaskNotificationLog.query.delete()
    YandexReportTaskLink.query.delete()
    YandexReport.query.delete()
    Task.query.delete()
    FileDocument.query.delete()
    Report.query.delete()
    Executor.query.delete()
    db.session.commit()

    return {"before": before, "after": kchs_data_counts()}
