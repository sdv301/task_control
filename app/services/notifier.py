import os
import smtplib
import ssl
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime

from services.task_timing import (
    days_word,
    format_late_label,
    overdue_days_from_deadline,
    safe_deadline,
)
from services.email_templates import (
    build_district_email_html,
    build_district_email_plain,
    inject_support,
    task_notification_rows,
)

SMTP_SERVER = os.environ.get("SMTP_SERVER", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or "587")
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "portal@local").strip()
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "No Reply").strip()
SMTP_SUPPORT_EMAIL = os.environ.get("SMTP_SUPPORT_EMAIL", SMTP_FROM or SMTP_USER or "").strip()
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() in ("1", "true", "yes")


def _from_header():
    return formataddr((SMTP_FROM_NAME, SMTP_FROM))


def _build_message(to_email, subject, html_body, plain_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _from_header()
    msg["To"] = to_email
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"
    if SMTP_SUPPORT_EMAIL:
        msg["Reply-To"] = SMTP_SUPPORT_EMAIL
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _compose_district_email(district_name, content_rows, note=None, badge=None):
    support = SMTP_SUPPORT_EMAIL or SMTP_FROM
    html_body = inject_support(
        build_district_email_html(district_name, content_rows, note=note, badge=badge),
        support,
    )
    plain_body = build_district_email_plain(
        district_name, content_rows, note=note, support_email=support,
    )
    return html_body, plain_body


def _compose_plain_email(body_text):
    support = SMTP_SUPPORT_EMAIL or SMTP_FROM
    plain = (body_text or "").strip() + (
        f"\n\n---\nЭто автоматическое письмо — не отвечайте на него.\nПо вопросам: {support}"
    )
    html = f"<html><body style='font-family:Arial,sans-serif;font-size:14px;color:#334155;'>"
    html += f"<pre style='white-space:pre-wrap;font-family:Arial,sans-serif;'>{plain}</pre></body></html>"
    return html, plain


def _smtp_configured():
    return bool(SMTP_SERVER and SMTP_FROM)


def get_smtp_status():
    return {
        "configured": _smtp_configured(),
        "server": SMTP_SERVER or None,
        "port": SMTP_PORT,
        "from": SMTP_FROM or None,
        "from_name": SMTP_FROM_NAME or None,
        "support_email": SMTP_SUPPORT_EMAIL or None,
        "user": SMTP_USER or None,
        "has_password": bool(SMTP_PASSWORD),
        "use_tls": SMTP_USE_TLS,
        "use_ssl": SMTP_USE_SSL,
    }


def _friendly_smtp_error(exc):
    msg = str(exc)
    if "Connection refused" in msg or "Errno 111" in msg:
        return f"SMTP-сервер {SMTP_SERVER}:{SMTP_PORT} недоступен (connection refused)."
    if "Authentication unsuccessful" in msg or "535" in msg or "parol prilozheniya" in msg.lower() or "application password" in msg.lower():
        return (
            "Ошибка авторизации Mail.ru: нужен пароль для внешних приложений. "
            "SMTP_USER и SMTP_FROM должны совпадать с ящиком @mail.ru / @bk.ru."
        )
    if "CERTIFICATE_VERIFY_FAILED" in msg:
        return "Ошибка SSL-сертификата SMTP-сервера."
    return msg


def _send_raw_email(to_email, subject, html_body, plain_body):
    msg = _build_message(to_email, subject, html_body, plain_body)
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
    except Exception as e:
        raise RuntimeError(_friendly_smtp_error(e)) from e


def send_test_email(to_email, template="district_reminder"):
    to_email = (to_email or "").strip().lower()
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "Укажите корректный email"}, 400

    if not _smtp_configured():
        return {
            "ok": False,
            "error": "SMTP не настроен. Задайте SMTP_SERVER и SMTP_FROM.",
            "smtp": get_smtp_status(),
        }, 400

    template = (template or "district_reminder").strip().lower()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    if template == "smtp":
        subject = "Портал КЧС — тест SMTP"
        body = f"Проверка отправки.\nВремя: {now}\nОтправитель: {_from_header()}"
        html, plain = _compose_plain_email(body)
    else:
        district_name = "Вилюйский улус (район)"
        subject = "КЧС: напоминание о сдаче отчёта (тест)"
        rows = task_notification_rows(
            task_title="Организовать мероприятия по пункту 4.1 протокола КЧС",
            item_number="4.1",
            deadline_str="20.03.2026",
            status_line="В работе",
            extra="До срока осталось 3 дня",
        )
        html, plain = _compose_district_email(
            district_name,
            rows,
            note="Это тестовое письмо — так будут выглядеть напоминания для районов.",
            badge="Тест",
        )

    try:
        _send_raw_email(to_email, subject, html, plain)
        logging.info("Тестовое письмо (%s) отправлено: %s", template, to_email)
        return {
            "ok": True,
            "message": f"Письмо «{template}» отправлено на {to_email}",
            "template": template,
            "smtp": get_smtp_status(),
        }, 200
    except Exception as e:
        logging.error("Ошибка тестового письма %s: %s", to_email, e)
        return {"ok": False, "error": str(e), "smtp": get_smtp_status()}, 500


def send_notification(email, subject, body, district_name=None, content_rows=None):
    if not email:
        logging.warning("Не указан email для рассылки.")
        return False

    if not _smtp_configured():
        logging.warning("SMTP не настроен. Письмо не отправлено: %s — %s", email, subject)
        return False

    try:
        if content_rows is not None:
            html, plain = _compose_district_email(district_name, content_rows)
        elif district_name:
            html, plain = _compose_district_email(
                district_name,
                [("Сообщение", body.replace("\n", " ").strip())],
            )
        else:
            html, plain = _compose_plain_email(body)
        _send_raw_email(email, subject, html, plain)
        logging.info("Письмо отправлено: %s — %s", email, subject)
        return True
    except Exception as e:
        logging.error("Ошибка при отправке письма %s: %s", email, e)
        return False


def _already_sent(TaskNotificationLog, task_id, notification_type):
    return TaskNotificationLog.query.filter_by(task_id=task_id, notification_type=notification_type).first() is not None


def _task_notify_context(task, now):
    executor = task.executor.name if task.executor else "Не назначен"
    deadline = safe_deadline(task)
    deadline_str = deadline.strftime("%d.%m.%Y") if deadline else "не указан"
    return executor, deadline_str


def _build_overdue_digest_body(tasks, now):
    lines = [
        f"Сводка просроченных поручений КЧС — {now.strftime('%d.%m.%Y %H:%M')}",
        "",
    ]
    if not tasks:
        lines.append("Просроченных поручений нет.")
        return "\n".join(lines)

    lines.append(f"Всего просрочено: {len(tasks)}")
    lines.append("")
    for task in tasks:
        executor, deadline_str = _task_notify_context(task, now)
        late_days = overdue_days_from_deadline(safe_deadline(task), now)
        late_part = format_late_label(late_days) or ""
        lines.append(f"• [{task.item_number or '—'}] {task.title}")
        lines.append(f"  {executor} · срок {deadline_str}" + (f" · {late_part}" if late_part else ""))
    return "\n".join(lines)


def send_overdue_digest(app):
    from models import db, Task, NotificationSettings, NotificationRecipient

    with app.app_context():
        settings = NotificationSettings.query.first()
        if settings and not settings.enable_email:
            return {"ok": False, "error": "Email-уведомления отключены"}, 400
        if not _smtp_configured():
            return {"ok": False, "error": "SMTP не настроен"}, 400

        recipients = [r.email for r in NotificationRecipient.query.filter_by(is_active=True).all() if r.email]
        if not recipients:
            return {"ok": False, "error": "Добавьте получателей в админке"}, 400

        now = datetime.now()
        overdue_tasks = [
            t for t in Task.query.filter(Task.status != "Выполнено").all()
            if safe_deadline(t) and safe_deadline(t) < now
        ]
        subject = f"КЧС: сводка просроченных ({len(overdue_tasks)}) — {now.strftime('%d.%m.%Y')}"
        body = _build_overdue_digest_body(overdue_tasks, now)

        sent = sum(1 for addr in recipients if send_notification(addr, subject, body))
        if sent == 0:
            return {"ok": False, "error": "Не удалось отправить"}, 500
        return {"ok": True, "message": f"Сводка отправлена {sent} получателям", "overdue_count": len(overdue_tasks)}, 200


def check_deadlines_and_notify(app):
    from models import db, Task, NotificationSettings, NotificationRecipient, TaskNotificationLog

    stats = {"notified": 0, "overdue_marked": 0, "skipped": 0}

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
            rows = None
            executor, deadline_str = _task_notify_context(task, now)

            if days_left < 0:
                task.status = "Просрочено"
                stats["overdue_marked"] += 1
                late_label = format_late_label(abs(days_left))
                notify_type = "overdue"
                subject = f"КЧС: просрочено — {task.title[:60]}"
                rows = task_notification_rows(
                    task.title, task.item_number, deadline_str, "Просрочено", late_label,
                )
            elif days_left <= 3 and settings.notify_days_3:
                notify_type = "due_3"
                subject = f"КЧС: срок через {days_left} {days_word(days_left)}"
                rows = task_notification_rows(
                    task.title, task.item_number, deadline_str, "В работе",
                    f"До срока осталось {days_left} {days_word(days_left)}",
                )
            elif days_left <= 7 and settings.notify_days_7:
                notify_type = "due_7"
                subject = f"КЧС: срок через {days_left} {days_word(days_left)}"
                rows = task_notification_rows(
                    task.title, task.item_number, deadline_str, "В работе",
                    f"До срока осталось {days_left} {days_word(days_left)}",
                )

            if not notify_type or _already_sent(TaskNotificationLog, task.id, notify_type):
                stats["skipped"] += 1
                continue

            if settings.enable_email:
                to_notify = set(recipients)
                if task.executor and task.executor.email:
                    to_notify.add(task.executor.email)
                sent_any = False
                for addr in to_notify:
                    if send_notification(addr, subject, None, district_name=executor, content_rows=rows):
                        sent_any = True
                if not sent_any and not _smtp_configured():
                    logging.info("LOCAL NOTIFY [%s] %s", notify_type, task.title)
            else:
                logging.info("LOCAL NOTIFY [%s] %s", notify_type, task.title)

            db.session.add(TaskNotificationLog(
                task_id=task.id,
                notification_type=notify_type,
                channel="email" if settings.enable_email else "local",
            ))
            stats["notified"] += 1

        db.session.commit()
        return stats


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from main import app
    print(check_deadlines_and_notify(app))
