from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Executor(db.Model):
    __tablename__ = 'executors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    email = db.Column(db.String(255))
    district = db.Column(db.String(255))
    tasks = db.relationship('Task', backref='executor', lazy=True)

class District(db.Model):
    __tablename__ = 'districts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    yandex_url = db.Column(db.String(500))
    total_tasks = db.Column(db.Integer, default=0)
    completed_tasks = db.Column(db.Integer, default=0)
    overdue_tasks = db.Column(db.Integer, default=0)
    timely_tasks = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    item_number = db.Column(db.String(50))
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

    __table_args__ = (db.UniqueConstraint('file_hash', 'item_number', name='_file_item_uc'),)

class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    target_period = db.Column(db.String(255))

class FileDocument(db.Model):
    __tablename__ = 'file_documents'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_hash = db.Column(db.String(255))
    doc_number = db.Column(db.String(100))
    doc_date = db.Column(db.String(100))
    file_data = db.Column(db.LargeBinary, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

