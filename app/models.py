from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Executor(db.Model):
    __tablename__ = 'executors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    email = db.Column(db.String(255))
    tasks = db.relationship('Task', backref='executor', lazy=True)

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    item_number = db.Column(db.String(500))
    title = db.Column(db.String(255), nullable=False)
    text = db.Column(db.Text)
    deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), default="В работе")
    report_submitted = db.Column(db.Boolean, default=False)
    file_hash = db.Column(db.String(255), nullable=False)
    executor_id = db.Column(db.Integer, db.ForeignKey('executors.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('file_documents.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    document = db.relationship('FileDocument', backref='tasks')

    __table_args__ = (db.UniqueConstraint('file_hash', 'item_number', 'executor_id', name='_file_item_exec_uc'),)

    @property
    def display_executor(self):
        """Имя исполнителя для groupby в шаблоне."""
        return self.executor.name if self.executor else 'Не назначен'

    @property
    def is_mass_task(self):
        """Является ли задача массовой (один пункт → несколько исполнителей)."""
        if not self.document_id or not self.item_number:
            return False
        count = Task.query.filter_by(
            document_id=self.document_id,
            item_number=self.item_number
        ).count()
        return count > 1

class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    target_period = db.Column(db.String(255))

class YandexReport(db.Model):
    """Отчёты, полученные с Яндекс.Диска"""
    __tablename__ = 'yandex_reports'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(500), nullable=False)
    yandex_path = db.Column(db.String(1000), nullable=False)
    sender_name = db.Column(db.String(255))
    received_at = db.Column(db.DateTime)
    file_hash = db.Column(db.String(255), unique=True)
    executor_id = db.Column(db.Integer, db.ForeignKey('executors.id'))
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='SET NULL'))
    kchs_number = db.Column(db.String(50))
    parsed_item_numbers = db.Column(db.Text)
    items_matched = db.Column(db.Integer, default=0)
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)
    parsed_sections = db.Column(db.Text)
    match_details = db.Column(db.Text)
    file_version = db.Column(db.Integer, default=1)
    superseded_by_id = db.Column(db.Integer, db.ForeignKey('yandex_reports.id'))
    completeness_status = db.Column(db.String(20), default='none')

    executor = db.relationship('Executor', backref='yandex_reports')
    task = db.relationship('Task', backref=db.backref('yandex_reports', passive_deletes=True))


class YandexReportTaskLink(db.Model):
    """Связь отчёта с несколькими поручениями (один PDF — несколько пунктов)."""
    __tablename__ = 'yandex_report_task_links'
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('yandex_reports.id', ondelete='CASCADE'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    linked_at = db.Column(db.DateTime, default=datetime.utcnow)
    match_method = db.Column(db.String(20), default='auto')
    confidence = db.Column(db.Float, default=1.0)

    report = db.relationship(
        'YandexReport',
        backref=db.backref('task_links', cascade='all, delete-orphan', passive_deletes=True),
    )
    task = db.relationship('Task', backref='yandex_report_links')

    __table_args__ = (db.UniqueConstraint('report_id', 'task_id', name='_report_task_uc'),)


class FileDocument(db.Model):
    __tablename__ = 'file_documents'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_hash = db.Column(db.String(255))
    doc_number = db.Column(db.String(100))
    doc_date = db.Column(db.String(100))
    file_data = db.Column(db.LargeBinary, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class NotificationSettings(db.Model):
    __tablename__ = 'notification_settings'
    id = db.Column(db.Integer, primary_key=True)
    enable_email = db.Column(db.Boolean, default=False)
    enable_telegram = db.Column(db.Boolean, default=False)  # заглушка до интеграции
    enable_deadline_colors = db.Column(db.Boolean, default=True)
    notify_days_7 = db.Column(db.Boolean, default=True)
    notify_days_3 = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NotificationRecipient(db.Model):
    __tablename__ = 'notification_recipients'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TaskNotificationLog(db.Model):
    __tablename__ = 'task_notification_logs'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)  # due_7, due_3, overdue
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    channel = db.Column(db.String(20), default='local')

    task = db.relationship(
        'Task',
        backref=db.backref('notification_logs', cascade='all, delete-orphan', passive_deletes=True),
    )

