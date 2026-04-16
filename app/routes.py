from flask import Blueprint, request, jsonify
from models import db, Task, Executor, FileDocument
from pdf_parser.pdf_engine import parse_pdf
import hashlib

main = Blueprint('main', __name__)

@main.route('/upload_protocol', methods=['POST'])
def upload_protocol():
    if 'file' not in request.files:
        return jsonify({"error": "Файл не найден"}), 400
    
    file = request.files['file']
    file_bytes = file.read()
    file_hash = hashlib.md5(file_bytes).hexdigest()
    
    # 1. Сохраняем документ для истории
    new_doc = FileDocument.query.filter_by(file_hash=file_hash).first()
    if not new_doc:
        new_doc = FileDocument(
            filename=file.filename,
            file_hash=file_hash,
            file_data=file_bytes
        )
        db.session.add(new_doc)
        db.session.flush()

    # 2. Запускаем наш парсер
    result = parse_pdf(file_bytes=file_bytes, filename=file.filename)
    
    if not result or not result.get('tasks'):
        return jsonify({"error": "Не удалось распарсить PDF или файлы не содержат задач"}), 500

    # Обновляем метаданные документа
    new_doc.doc_number = result.get('doc_number')
    new_doc.doc_date = result.get('doc_date')

    parsed_tasks = result['tasks']
    new_tasks_count = 0
    
    for t_data in parsed_tasks:
        # 1. Проверяем/Создаем исполнителя
        executor_name = t_data['executor']
        executor = Executor.query.filter_by(name=executor_name).first()
        if not executor:
            executor = Executor(name=executor_name)
            db.session.add(executor)
            db.session.flush() # Получаем ID

        # 2. Проверяем дубликаты (хэш файла + номер пункта + ID исполнителя)
        item_num = t_data.get('item_number', t_data.get('title'))
        exists = Task.query.filter_by(
            file_hash=file_hash, 
            item_number=item_num,
            executor_id=executor.id
        ).first()
        
        if not exists:
            new_task = Task(
                item_number=item_num,
                title=t_data['title'],
                text=t_data.get('text', ''),
                deadline=t_data['deadline'],
                file_hash=file_hash,
                executor_id=executor.id,
                document_id=new_doc.id
            )
            db.session.add(new_task)
            new_tasks_count += 1

    db.session.commit()
    return jsonify({
        "message": f"Обработано. Добавлено {new_tasks_count} новых пунктов.",
        "doc_number": new_doc.doc_number,
        "new_count": new_tasks_count
    }), 201