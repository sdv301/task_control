from flask import Blueprint, request, jsonify
from .models import db, Task, Executor
from .app_parser.pdf_engine import parse_pdf # Твой обновленный парсер

main = Blueprint('main', __name__)

@main.route('/upload_protocol', methods=['POST'])
def upload_protocol():
    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден"}), 400
    
    file = request.files['file']
    file_bytes = file.read()
    
    # Запускаем наш парсер, который возвращает список задач
    parsed_tasks = parse_pdf(file_bytes=file_bytes, filename=file.filename)
    
    if not parsed_tasks:
        return jsonify({"error": "Не удалось распарсить PDF"}), 500

    new_tasks_count = 0
    for t_data in parsed_tasks:
        # 1. Проверяем/Создаем исполнителя
        executor = Executor.query.filter_by(name=t_data['executor']).first()
        if not executor:
            executor = Executor(name=t_data['executor'])
            db.session.add(executor)
            db.session.commit() # Фиксируем, чтобы получить ID

        # 2. Проверяем, не загружали ли мы этот пункт ранее
        exists = Task.query.filter_by(file_hash=t_data['file_hash'], item_number=t_data['title']).first()
        if not exists:
            new_task = Task(
                item_number=t_data['title'],
                title=f"Поручение {t_data['title']}",
                text=t_data['text'],
                deadline=t_data['deadline'],
                file_hash=t_data['file_hash'],
                executor_id=executor.id
            )
            db.session.add(new_task)
            new_tasks_count += 1

    db.session.commit()
    return jsonify({"message": f"Обработано. Добавлено {new_tasks_count} новых пунктов."}), 201