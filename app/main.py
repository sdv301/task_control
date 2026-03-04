import os
import logging
from flask import Flask, render_template
from models import db, Task, Executor

# Настройка логирования
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

# Конфигурация БД (PostgreSQL из docker-compose)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///tasks.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

import time

# Инициализация БД
with app.app_context():
    retries = 5
    while retries > 0:
        try:
            db.create_all()
            logging.info("Successfully connected to the database and created tables.")
            break
        except Exception as e:
            logging.warning(f"Database not ready. Retrying in 3 seconds... ({retries} left). Error: {e}")
            time.sleep(3)
            retries -= 1

@app.route('/')
def dashboard():
    tasks = Task.query.all()
    # Простая логика обновления статуса (лучше делать фоново)
    from datetime import datetime
    for task in tasks:
        if task.status != "Выполнено" and task.deadline < datetime.utcnow():
             task.status = "Просрочено"
    db.session.commit()
    
    return render_template('dashboard.html', tasks=tasks)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
