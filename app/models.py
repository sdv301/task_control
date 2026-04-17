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
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)

    executor = db.relationship('Executor', backref='yandex_reports')
    task = db.relationship('Task', backref='yandex_reports')


class FileDocument(db.Model):
    __tablename__ = 'file_documents'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_hash = db.Column(db.String(255))
    doc_number = db.Column(db.String(100))
    doc_date = db.Column(db.String(100))
    file_data = db.Column(db.LargeBinary, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

