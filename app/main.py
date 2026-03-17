import os
import logging
import time
import hashlib
import io
from datetime import datetime, timedelta
from collections import OrderedDict

from flask import Flask, render_template, jsonify, request, redirect, url_for, send_file
from models import db, Task, Executor, FileDocument
from parser.pdf_engine import parse_pdf

# ─── Логирование ─────────────────────────────────────────────────────────────
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ─── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:////data/tasks.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
db.init_app(app)

# ─── Инициализация БД ────────────────────────────────────────────────────────
with app.app_context():
    os.makedirs('/data', exist_ok=True)
    db.create_all()
    logging.info("БД инициализирована успешно.")


def _refresh_statuses(tasks, now):
    changed = False
    for task in tasks:
        if task.status != "Выполнено" and task.deadline < now:
            task.status = "Просрочено"
            changed = True
    if changed:
        db.session.commit()


# ─── Главная страница ─────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


# ─── Загрузка PDF ─────────────────────────────────────────────────────────────
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'document' not in request.files:
        return jsonify({"error": "Файл не найден в запросе"}), 400

    file = request.files['document']
    if not file or file.filename == '':
        return jsonify({"error": "Файл не выбран"}), 400

    file_bytes = file.read()
    file_hash = hashlib.md5(file_bytes).hexdigest()

    # Сохранение документа
    new_doc = FileDocument(filename=file.filename, file_data=file_bytes, file_hash=file_hash)
    db.session.add(new_doc)
    db.session.flush()

    # Парсинг
    result = parse_pdf(file_bytes=file_bytes, filename=file.filename)
    if not result:
        db.session.rollback()
        return jsonify({"error": "Не удалось распознать пункты из PDF. Проверьте формат файла."}), 422

    # Сохраняем номер и дату документа
    parsed_tasks = result.get('tasks', [])
    new_doc.doc_number = result.get('doc_number')
    new_doc.doc_date = result.get('doc_date')

    new_count = 0
    for t_data in parsed_tasks:
        executor = Executor.query.filter_by(name=t_data['executor']).first()
        if not executor:
            executor = Executor(name=t_data['executor'])
            db.session.add(executor)
            db.session.flush()

        exists = Task.query.filter_by(
            file_hash=t_data['file_hash'],
            item_number=t_data['title']
        ).first()

        if not exists:
            new_task = Task(
                item_number=t_data['title'],
                title=t_data['title'],
                text=t_data.get('text', ''),
                deadline=t_data['deadline'],
                file_hash=t_data['file_hash'],
                executor_id=executor.id,
                document_id=new_doc.id
            )
            db.session.add(new_task)
            new_count += 1

    db.session.commit()
    logging.info(f"Загружен файл '{file.filename}': добавлено {new_count} новых задач.")
    return jsonify({"message": f"Успешно! Добавлено {new_count} новых поручений.", "count": new_count}), 201


# ─── Дашборд ──────────────────────────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    search_q = request.args.get('q', '').strip()

    all_tasks = Task.query.order_by(Task.deadline.asc()).all()
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)
    _refresh_statuses(all_tasks, now)

    # Применяем поиск
    if search_q:
        q_lower = search_q.lower()
        filtered_tasks = [
            t for t in all_tasks
            if q_lower in (t.title or '').lower()
            or q_lower in (t.text or '').lower()
            or q_lower in (t.executor.name or '').lower()
            or (t.document and q_lower in (t.document.filename or '').lower())
        ]
    else:
        filtered_tasks = all_tasks

    # Группировка по документам
    documents = OrderedDict()
    orphan_tasks = []

    for task in filtered_tasks:
        if task.document_id and task.document:
            doc_id = task.document_id
            if doc_id not in documents:
                doc = task.document
                documents[doc_id] = {
                    'id': doc.id,
                    'filename': doc.filename,
                    'uploaded_at': doc.uploaded_at,
                    'doc_number': doc.doc_number,
                    'doc_date': doc.doc_date,
                    'tasks': [],
                    'total': 0,
                    'overdue': 0,
                    'completed': 0,
                }
            documents[doc_id]['tasks'].append(task)
            documents[doc_id]['total'] += 1
            if task.status == 'Просрочено':
                documents[doc_id]['overdue'] += 1
            elif task.status == 'Выполнено':
                documents[doc_id]['completed'] += 1
        else:
            orphan_tasks.append(task)

    doc_list = list(documents.values())

    # Статистика по ВСЕМ (не отфильтрованным)
    total = len(all_tasks)
    overdue = sum(1 for t in all_tasks if t.status == 'Просрочено')
    completed = sum(1 for t in all_tasks if t.status == 'Выполнено')
    in_progress = total - overdue - completed
    percentage = int((completed / total * 100) if total > 0 else 0)

    # Статистика за год
    current_year = now.year
    year_tasks = [t for t in all_tasks if t.created_at and t.created_at.year == current_year]
    year_docs = FileDocument.query.filter(
        db.extract('year', FileDocument.uploaded_at) == current_year
    ).count()

    stats = {
        'total': total,
        'overdue': overdue,
        'completed': completed,
        'percentage': percentage,
        'in_progress': in_progress,
        'year_docs': year_docs,
        'year_tasks': len(year_tasks),
        'current_year': current_year,
    }

    return render_template(
        'dashboard.html',
        documents=doc_list,
        orphan_tasks=orphan_tasks,
        stats=stats,
        search_q=search_q,
        tomorrow=tomorrow.date(),
        today=now.date()
    )


# ─── Добавить задачу вручную ──────────────────────────────────────────────────
@app.route('/task/add', methods=['GET', 'POST'])
def add_task():
    if request.method == 'POST':
        executor_name = request.form.get('executor', '').strip()
        title        = request.form.get('title', '').strip()
        text         = request.form.get('text', '').strip()
        deadline_str = request.form.get('deadline', '').strip()

        if not executor_name or not title or not deadline_str:
            return render_template('add_task.html', error="Заполните все обязательные поля.")

        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
        except ValueError:
            return render_template('add_task.html', error="Неверный формат даты.")

        executor = Executor.query.filter_by(name=executor_name).first()
        if not executor:
            executor = Executor(name=executor_name)
            db.session.add(executor)
            db.session.flush()

        fake_hash = hashlib.md5(f"manual-{title}-{datetime.utcnow().isoformat()}".encode()).hexdigest()
        task = Task(
            item_number="Ручной ввод",
            title=title,
            text=text,
            deadline=deadline,
            file_hash=fake_hash,
            executor_id=executor.id
        )
        db.session.add(task)
        db.session.commit()
        logging.info(f"Задача '{title}' добавлена вручную.")
        return redirect(url_for('dashboard'))

    return render_template('add_task.html')


# ─── Изменить статус задачи ───────────────────────────────────────────────────
@app.route('/task/<int:task_id>/status', methods=['POST'])
def update_status(task_id):
    task = Task.query.get_or_404(task_id)
    new_status = request.json.get('status')
    if new_status == 'Выполнено' and not task.report_submitted:
        return jsonify({"error": "Сначала внесите отчёт", "need_report": True}), 400
    if new_status in ('В работе', 'Выполнено', 'Просрочено'):
        task.status = new_status
        db.session.commit()
        return jsonify({"ok": True, "status": new_status})
    return jsonify({"error": "Недопустимый статус"}), 400


@app.route('/task/<int:task_id>/report', methods=['POST'])
def toggle_report(task_id):
    task = Task.query.get_or_404(task_id)
    task.report_submitted = not task.report_submitted
    db.session.commit()
    return jsonify({"ok": True, "report_submitted": task.report_submitted})


@app.route('/document/<int:doc_id>/delete', methods=['POST'])
def delete_document(doc_id):
    doc = FileDocument.query.get_or_404(doc_id)
    # Удаляем все задачи этого документа
    Task.query.filter_by(document_id=doc_id).delete()
    db.session.delete(doc)
    db.session.commit()
    logging.info(f"Удалён документ '{doc.filename}' (id={doc_id}) и все его задачи.")
    return jsonify({"ok": True})


# ─── Экспорт в Excel ──────────────────────────────────────────────────────────
@app.route('/export/excel')
def export_excel():
    try:
        import openpyxl
        from openpyxl.styles import (
            PatternFill, Font, Alignment, Border, Side
        )
        from openpyxl.utils import get_column_letter
    except ImportError:
        return jsonify({"error": "Модуль openpyxl не установлен."}), 500

    tasks = Task.query.order_by(Task.deadline.asc()).all()
    now = datetime.utcnow()
    _refresh_statuses(tasks, now)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Поручения"

    CLR_HEADER_BG  = "1E3A5F"
    CLR_HEADER_FG  = "FFFFFF"
    CLR_ROW_ODD    = "EBF1F8"
    CLR_ROW_EVEN   = "FFFFFF"
    CLR_OVERDUE    = "FFD7D7"
    CLR_COMPLETED  = "D4EDDA"
    CLR_TITLE_BG   = "2E75B6"
    CLR_SUBTTL_BG  = "D6E4F0"

    thin = Side(border_style="thin", color="AAAAAA")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells('A1:G1')
    title_cell = ws['A1']
    title_cell.value = "ИСПОЛНЕНИЕ ПОРУЧЕНИЙ"
    title_cell.font = Font(bold=True, size=14, color=CLR_HEADER_FG, name="Calibri")
    title_cell.fill = PatternFill("solid", fgColor=CLR_TITLE_BG)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells('A2:G2')
    date_cell = ws['A2']
    date_cell.value = f"Сформировано: {now.strftime('%d.%m.%Y %H:%M')} UTC"
    date_cell.font = Font(italic=True, size=10, color="555555", name="Calibri")
    date_cell.fill = PatternFill("solid", fgColor=CLR_SUBTTL_BG)
    date_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[3].height = 6

    HEADERS = ["No", "Поручение / Пункт", "Текст поручения", "Исполнитель", "Срок исполнения", "Статус", "Дней до срока"]
    WIDTHS  = [5, 22, 50, 24, 18, 14, 14]

    for col_idx, (header, width) in enumerate(zip(HEADERS, WIDTHS), start=1):
        cell = ws.cell(row=4, column=col_idx, value=header)
        cell.font = Font(bold=True, size=11, color=CLR_HEADER_FG, name="Calibri")
        cell.fill = PatternFill("solid", fgColor=CLR_HEADER_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[4].height = 24
    ws.freeze_panes = "A5"

    for row_idx, task in enumerate(tasks, start=1):
        excel_row = row_idx + 4
        deadline_date = task.deadline.date()
        days_left = (deadline_date - now.date()).days

        if task.status == 'Просрочено':
            row_color = CLR_OVERDUE
        elif task.status == 'Выполнено':
            row_color = CLR_COMPLETED
        else:
            row_color = CLR_ROW_ODD if row_idx % 2 == 1 else CLR_ROW_EVEN

        fill = PatternFill("solid", fgColor=row_color)
        days_str = f"+{days_left}" if days_left >= 0 else str(days_left)

        row_data = [
            row_idx,
            task.title or "-",
            task.text or "-",
            task.executor.name if task.executor else "-",
            deadline_date.strftime('%d.%m.%Y'),
            task.status,
            days_str,
        ]

        for col_idx, value in enumerate(row_data, start=1):
            cell = ws.cell(row=excel_row, column=col_idx, value=value)
            cell.fill = fill
            cell.border = border
            cell.font = Font(size=10, name="Calibri")
            cell.alignment = Alignment(
                vertical="center",
                wrap_text=(col_idx == 3),
                horizontal="center" if col_idx not in (2, 3, 4) else "left"
            )
            if col_idx == 7 and days_left < 0:
                cell.font = Font(size=10, name="Calibri", color="CC0000", bold=True)

        ws.row_dimensions[excel_row].height = 30

    total = len(tasks)
    completed_cnt = sum(1 for t in tasks if t.status == 'Выполнено')
    overdue_cnt   = sum(1 for t in tasks if t.status == 'Просрочено')
    inprog_cnt    = total - completed_cnt - overdue_cnt

    summary_row = len(tasks) + 5
    ws.merge_cells(f'A{summary_row}:C{summary_row}')
    ws[f'A{summary_row}'].value = f"ИТОГО: {total} поручений"
    ws[f'A{summary_row}'].font = Font(bold=True, size=11, name="Calibri")
    ws[f'A{summary_row}'].fill = PatternFill("solid", fgColor=CLR_SUBTTL_BG)
    ws[f'A{summary_row}'].alignment = Alignment(horizontal="left", vertical="center")
    ws[f'A{summary_row}'].border = border

    ws[f'D{summary_row}'].value = f"В работе: {inprog_cnt}"
    ws[f'E{summary_row}'].value = f"Выполнено: {completed_cnt}"
    ws[f'F{summary_row}'].value = f"Просрочено: {overdue_cnt}"
    for col in ['D', 'E', 'F', 'G']:
        ws[f'{col}{summary_row}'].font = Font(bold=True, size=10, name="Calibri")
        ws[f'{col}{summary_row}'].fill = PatternFill("solid", fgColor=CLR_SUBTTL_BG)
        ws[f'{col}{summary_row}'].alignment = Alignment(horizontal="center", vertical="center")
        ws[f'{col}{summary_row}'].border = border
    ws.row_dimensions[summary_row].height = 22

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"Porycheniya_{now.strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


# ─── API: статистика ─────────────────────────────────────────────────────────
@app.route('/api/stats')
def api_stats():
    tasks = Task.query.all()
    now = datetime.utcnow()
    _refresh_statuses(tasks, now)
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == 'Выполнено')
    overdue   = sum(1 for t in tasks if t.status == 'Просрочено')
    return jsonify({
        "total": total,
        "completed": completed,
        "overdue": overdue,
        "in_progress": total - completed - overdue
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
