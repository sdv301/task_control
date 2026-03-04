from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Executor(db.Model):
    __tablename__ = 'executors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255))
    tasks = db.relationship('Task', backref='executor', lazy=True)

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    text = db.Column(db.Text)
    deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), default="В работе") # В работе, Просрочено, Выполнено
    file_hash = db.Column(db.String(255), unique=True, nullable=False)
    executor_id = db.Column(db.Integer, db.ForeignKey('executors.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    target_period = db.Column(db.String(255))
