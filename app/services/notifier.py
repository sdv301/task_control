import os
import smtplib
from email.mime.text import MIMEText
import logging
from datetime import datetime

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.example.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "test@example.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "password")

def send_notification(email, subject, body):
    if not email:
        logging.warning("Не указан email для рассылки.")
        return
        
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = email

    try:
        # Для тестирования мы можем просто залогировать сообщение без реальной отправки
        logging.info(f"MOCK ОТПРАВКА: Отправлено письмо {email}. Тема: {subject}")
        # server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        # server.starttls()
        # server.login(SMTP_USER, SMTP_PASSWORD)
        # server.send_message(msg)
        # server.quit()
    except Exception as e:
        logging.error(f"Ошибка при отправке письма: {str(e)}")

def check_deadlines_and_notify(app):
    """Проверка дедлайнов и отправка уведомлений.
    Принимает Flask app для контекста БД.
    """
    from models import db, Task

    with app.app_context():
        # Ищем задачи, срок которых истёк, но статус не "Выполнено"
        overdue_tasks = Task.query.filter(
            Task.status != "Выполнено",
            Task.deadline < datetime.utcnow()
        ).all()
        for task in overdue_tasks:
            task.status = "Просрочено"
            if task.executor and task.executor.email:
                send_notification(
                    task.executor.email,
                    f"Просрочена задача: {task.title}",
                    f"Уважаемый {task.executor.name}, срок задачи {task.title} истек {task.deadline}."
                )
        db.session.commit()

if __name__ == "__main__":
    # Заглушка для ручного запуска
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from main import app
    check_deadlines_and_notify(app)
