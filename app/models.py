from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Executor(db.Model):
    __tablename__ = 'executors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True) # Добавлена уникальность имени
    email = db.Column(db.String(255))
    tasks = db.relationship('Task', backref='exec_ref', lazy=True)

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    item_number = db.Column(db.String(50)) # Номер пункта из протокола (напр. 5.1)
    title = db.Column(db.String(255), nullable=False)
    text = db.Column(db.Text)
    deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), default="В работе")
    file_hash = db.Column(db.String(255), nullable=False) # Убрали unique=True
    executor_id = db.Column(db.Integer, db.ForeignKey('executors.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Уникальность теперь по паре: Хеш файла + Номер пункта
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
    file_data = db.Column(db.LargeBinary, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

