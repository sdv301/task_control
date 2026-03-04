import os
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from parser.pdf_engine import parse_pdf
from models import db, Task, Executor
from main import app # Для работы с контекстом БД

INPUT_DIR = "/Desktop/Input_Tasks"

class PDFHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.pdf'):
            logging.info(f"Обнаружен новый файл: {event.src_path}")
            time.sleep(1) # Ждем, пока файл полностью скопируется
            self.process_file(event.src_path)
            
    def process_file(self, file_path):
        parsed_data = parse_pdf(file_path)
        if parsed_data:
            with app.app_context():
                # Проверка на дубликаты
                existing_task = Task.query.filter_by(file_hash=parsed_data['file_hash']).first()
                if existing_task:
                    logging.info(f"Задача с хэшем {parsed_data['file_hash']} уже существует (Дубликат). Пропуск.")
                    return

                # Ищем или создаем исполнителя
                executor = Executor.query.filter_by(name=parsed_data['executor']).first()
                if not executor:
                    executor = Executor(name=parsed_data['executor'])
                    db.session.add(executor)
                    db.session.flush() # Получить ID

                new_task = Task(
                    title=parsed_data['title'],
                    text=parsed_data['text'],
                    deadline=parsed_data['deadline'],
                    file_hash=parsed_data['file_hash'],
                    executor_id=executor.id
                )
                db.session.add(new_task)
                db.session.commit()
                logging.info(f"Успешно добавлена задача: {new_task.title}")

def start_watcher():
    logging.info(f"Запуск мониторинга папки {INPUT_DIR}")
    if not os.path.exists(INPUT_DIR):
        os.makedirs(INPUT_DIR)
        
    event_handler = PDFHandler()
    observer = Observer()
    observer.schedule(event_handler, INPUT_DIR, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_watcher()
