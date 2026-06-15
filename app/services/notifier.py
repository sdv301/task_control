import os
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from datetime import datetime

SMTP_SERVER = os.environ.get("SMTP_SERVER", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or "587")
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "portal@local").strip()
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() in ("1", "true", "yes")


def _smtp_configured():
    return bool(SMTP_SERVER and SMTP_FROM)


def get_smtp_status():
    """Статус SMTP для админки (без пароля)."""
    return {
        "configured": _smtp_configured(),
        "server": SMTP_SERVER or None,
        "port": SMTP_PORT,
        "from": SMTP_FROM or None,
        "user": SMTP_USER or None,
        "has_password": bool(SMTP_PASSWORD),
        "use_tls": SMTP_USE_TLS,
        "use_ssl": SMTP_USE_SSL,
    }


def send_test_email(to_email):
    """Пример / проверка отправки письма."""
    to_email = (to_email or "").strip().lower()
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "Укажите корректный email"}, 400

    if not _smtp_configured():
        return {
            "ok": False,
            "error": "SMTP не настроен. Задайте SMTP_SERVER и SMTP_FROM в переменных окружения.",
            "smtp": get_smtp_status(),
        }, 400

    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    subject = "Портал КЧС — тестовое письмо"
    body = (
        "Это тестовое письмо от портала мониторинга КЧС.\n\n"
        f"Время отправки: {now}\n"
        f"SMTP-сервер: {SMTP_SERVER}:{SMTP_PORT}\n"
        f"Отправитель: {SMTP_FROM}\n\n"
        "Если вы получили это письмо — уведомления по email настроены правильно."
    )

    try:
        if SMTP_USE_SSL:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context, timeout=30) as server:
                if SMTP_USER and SMTP_PASSWORD:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                msg = MIMEText(body, "plain", "utf-8")
                msg["Subject"] = subject
                msg["From"] = SMTP_FROM
                msg["To"] = to_email
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
                server.ehlo()
                if SMTP_USE_TLS:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                if SMTP_USER and SMTP_PASSWORD:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                msg = MIMEText(body, "plain", "utf-8")
                msg["Subject"] = subject
                msg["From"] = SMTP_FROM
                msg["To"] = to_email
                server.send_message(msg)
        logging.info("Тестовое письмо отправлено: %s", to_email)
        return {
            "ok": True,
            "message": f"Письмо отправлено на {to_email}",
            "smtp": get_smtp_status(),
        }, 200
    except Exception as e:
        logging.error("Ошибка тестового письма %s: %s", to_email, e)
        return {
            "ok": False,
            "error": str(e),
            "smtp": get_smtp_status(),
        }, 500


def send_notification(email, subject, body):
    if not email:
        logging.warning("Не указан email для рассылки.")
        return False

    if not _smtp_configured():
        logging.warning(
            "SMTP не настроен (SMTP_SERVER / SMTP_FROM). Письмо не отправлено: %s — %s",
            email, subject,
        )
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = email

    try:
        if SMTP_USE_SSL:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context, timeout=30) as server:
                if SMTP_USER and SMTP_PASSWORD:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
                server.ehlo()
                if SMTP_USE_TLS:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                if SMTP_USER and SMTP_PASSWORD:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        logging.info("Письмо отправлено: %s — %s", email, subject)
        return True
    except Exception as e:
        logging.error("Ошибка при отправке письма %s: %s", email, e)
        return False


def _already_sent(TaskNotificationLog, task_id, notification_type):
    return TaskNotificationLog.query.filter_by(task_id=task_id, notification_type=notification_type).first() is not None


def check_deadlines_and_notify(app):
    """Локальная проверка дедлайнов + уведомления (email/заглушки)."""
    from models import db, Task, NotificationSettings, NotificationRecipient, TaskNotificationLog

    with app.app_context():
        settings = NotificationSettings.query.first()
        if not settings:
            settings = NotificationSettings()
            db.session.add(settings)
            db.session.flush()

        now = datetime.utcnow()
        recipients = [r.email for r in NotificationRecipient.query.filter_by(is_active=True).all() if r.email]
        tasks = Task.query.filter(Task.status != "Выполнено").all()

        for task in tasks:
            if not task.deadline or task.deadline.year >= 2099:
                continue
            days_left = (task.deadline.date() - now.date()).days
            notify_type = None
            subject = None
            body = None

            if days_left < 0:
                task.status = "Просрочено"
                notify_type = "overdue"
                subject = f"Просрочена задача: {task.title}"
                body = f"Задача '{task.title}' просрочена. Срок: {task.deadline.strftime('%d.%m.%Y')}."
            elif days_left <= 3 and settings.notify_days_3:
                notify_type = "due_3"
                subject = f"Срок через 3 дня: {task.title}"
                body = f"Задача '{task.title}' должна быть выполнена до {task.deadline.strftime('%d.%m.%Y')}."
            elif days_left <= 7 and settings.notify_days_7:
                notify_type = "due_7"
                subject = f"Срок через неделю: {task.title}"
                body = f"Задача '{task.title}' должна быть выполнена до {task.deadline.strftime('%d.%m.%Y')}."

            if not notify_type or _already_sent(TaskNotificationLog, task.id, notify_type):
                continue

            if settings.enable_email:
                to_notify = set(recipients)
                if task.executor and task.executor.email:
                    to_notify.add(task.executor.email)
                sent_any = False
                for addr in to_notify:
                    if send_notification(addr, subject, body):
                        sent_any = True
                if not sent_any and not _smtp_configured():
                    logging.info(f"LOCAL NOTIFY [{notify_type}] {task.title} ({task.deadline})")
            else:
                logging.info(f"LOCAL NOTIFY [{notify_type}] {task.title} ({task.deadline})")

            if settings.enable_telegram:
                logging.info(f"TELEGRAM STUB [{notify_type}] {task.title}")

            db.session.add(TaskNotificationLog(
                task_id=task.id,
                notification_type=notify_type,
                channel="email" if settings.enable_email else "local"
            ))
        db.session.commit()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from main import app
    check_deadlines_and_notify(app)
