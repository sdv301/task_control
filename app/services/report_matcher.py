"""
Автоматическая и полуавтоматическая привязка отчётов с Яндекс.Диска к поручениям.
"""
import json
import logging
import re
from difflib import SequenceMatcher

AUTO_LINK_MIN = 0.72
SUGGEST_MIN = 0.52

TITLE_SYNONYMS = {
    "адпи": "аварийно спасательные приборы индивидуальные",
    "омсу": "органы местного самоуправления",
    "кчс": "комиссия по предупреждению чрезвычайных ситуаций",
    "опб": "обеспечение пожарной безопасности",
    "дорожная карта": "план мероприятий",
    "гсм": "горюче смазочные материалы",
}


def apply_synonyms(text):
    result = (text or "").lower().replace("ё", "е")
    for short, full in TITLE_SYNONYMS.items():
        result = re.sub(rf'\b{re.escape(short)}\b', full, result)
    return result


def normalize_title(text):
    text = apply_synonyms(text)
    text = re.sub(r'пункт\s*\d+(?:\.\d+)*\.?\s*', ' ', text)
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()


def title_similarity(left, right):
    a = normalize_title(left)
    b = normalize_title(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return max(SequenceMatcher(None, a, b).ratio(), 0.78)
    return SequenceMatcher(None, a, b).ratio()


def score_task_match(task, item_numbers, sections):
    """Оценка совпадения поручения с отчётом: confidence 0..1, method."""
    from services.yandex_disk import (
        _task_matches_item_number, _extract_item_numbers, _normalize_item_number,
    )

    task_item = _normalize_item_number(task.item_number) or ""
    task_blob = f"{task.title or ''} {task.text or ''}"

    if _task_matches_item_number(task, item_numbers):
        return 1.0, "number", f"пункт {task_item}"

    best_ratio = 0.0
    best_section = None
    for section in sections or []:
        sec_item = _normalize_item_number(section.get("item_number")) or ""
        if task_item and sec_item and task_item != sec_item:
            continue
        ratio = title_similarity(task_blob, section.get("title", ""))
        if ratio > best_ratio:
            best_ratio = ratio
            best_section = sec_item

    if not sections and task_item and task_item in item_numbers:
        return 0.95, "number", f"пункт {task_item}"

    task_items = _extract_item_numbers(task_blob)
    if task_items & set(item_numbers or []):
        return 0.9, "number", f"пункт {task_item}"

    if best_ratio >= SUGGEST_MIN:
        return best_ratio, "title", f"название ~{int(best_ratio * 100)}% (п.{best_section or '?'})"

    return best_ratio, None, None


def build_match_plan(executor, response_meta):
    """План привязки: auto, suggest, пропущенные пункты."""
    from models import Task
    from services.yandex_disk import _filter_tasks_by_kchs_document, _task_has_yandex_link

    kchs_number = response_meta.get("kchs_number")
    item_numbers = set(response_meta.get("item_numbers") or [])
    sections = response_meta.get("sections") or []

    if not item_numbers and not sections:
        return {
            "auto": [], "suggest": [], "open_total": 0,
            "missing_tasks": [], "parsed_sections": sections,
        }

    all_tasks = Task.query.filter_by(executor_id=executor.id).order_by(Task.deadline.asc()).all()
    open_tasks = [t for t in all_tasks if not _task_has_yandex_link(t)]
    candidates = _filter_tasks_by_kchs_document(open_tasks, kchs_number)

    auto, suggest = [], []
    for task in candidates:
        confidence, method, detail = score_task_match(task, item_numbers, sections)
        entry = {
            "task_id": task.id,
            "item_number": task.item_number,
            "title": (task.title or "")[:120],
            "confidence": round(confidence, 3),
            "method": method,
            "detail": detail,
        }
        if method == "number" or confidence >= AUTO_LINK_MIN:
            auto.append(entry)
        elif confidence >= SUGGEST_MIN:
            suggest.append(entry)

    linked_ids = {e["task_id"] for e in auto + suggest}
    missing_tasks = [
        {
            "task_id": t.id,
            "item_number": t.item_number,
            "title": (t.title or "")[:120],
        }
        for t in candidates if t.id not in linked_ids
    ]

    return {
        "auto": auto,
        "suggest": suggest,
        "open_total": len(candidates),
        "missing_tasks": missing_tasks,
        "parsed_sections": [
            {"item_number": s.get("item_number"), "title": (s.get("title") or "")[:160]}
            for s in sections
        ],
    }


def apply_links(report, executor, tasks_with_meta, received_at):
    """Создать связи report↔task и обновить статусы."""
    from models import db, YandexReportTaskLink
    from services.yandex_disk import _apply_report_to_task

    if report.id is None:
        db.session.add(report)
        db.session.flush()
    if not report.id:
        return 0, []

    linked = 0
    link_records = []
    for task, method, confidence in tasks_with_meta:
        existing = YandexReportTaskLink.query.filter_by(
            report_id=report.id, task_id=task.id
        ).first()
        if not existing:
            link = YandexReportTaskLink(
                report_id=report.id,
                task_id=task.id,
                match_method=method or "auto",
                confidence=confidence,
            )
            db.session.add(link)
        else:
            existing.match_method = method or existing.match_method
            existing.confidence = confidence
        _apply_report_to_task(task, received_at)
        linked += 1
        link_records.append({
            "task_id": task.id,
            "item_number": task.item_number,
            "method": method,
            "confidence": confidence,
        })

    if tasks_with_meta:
        report.task_id = tasks_with_meta[0][0].id
    return linked, link_records


def store_extended_metadata(report, response_meta, plan, linked_count, link_records):
    report.kchs_number = response_meta.get("kchs_number")
    report.parsed_item_numbers = json.dumps(
        sorted(response_meta.get("item_numbers") or []), ensure_ascii=False
    )
    report.parsed_sections = json.dumps(plan.get("parsed_sections") or [], ensure_ascii=False)
    report.items_matched = linked_count
    report.match_details = json.dumps({
        "auto": plan.get("auto", []),
        "suggest": plan.get("suggest", []),
        "linked": link_records,
        "missing_tasks": plan.get("missing_tasks", []),
    }, ensure_ascii=False)

    open_total = plan.get("open_total") or 0
    if linked_count == 0:
        report.completeness_status = "none"
    elif linked_count >= open_total and open_total > 0:
        report.completeness_status = "full"
    elif linked_count > 0:
        report.completeness_status = "partial"
    else:
        report.completeness_status = "none"


def auto_link_report(report, executor, file_info, response_meta, include_suggestions=False):
    """Автопривязка: высокая уверенность сразу, средняя — по запросу."""
    from models import Task, db
    from services.yandex_disk import _parse_received_at

    plan = build_match_plan(executor, response_meta)
    received_at = report.received_at or _parse_received_at(file_info)
    report.executor_id = executor.id

    if report.id is None:
        db.session.add(report)
        db.session.flush()

    to_link = list(plan["auto"])
    if include_suggestions:
        to_link.extend(plan["suggest"])

    tasks_with_meta = []
    for entry in to_link:
        task = Task.query.get(entry["task_id"])
        if task:
            tasks_with_meta.append((task, entry.get("method"), entry.get("confidence")))

    if tasks_with_meta:
        linked, link_records = apply_links(report, executor, tasks_with_meta, received_at)
    else:
        linked, link_records = 0, []

    store_extended_metadata(report, response_meta, plan, linked, link_records)
    return {
        "linked": linked,
        "auto_count": len(plan["auto"]),
        "suggest_count": len(plan["suggest"]),
        "missing_count": len(plan["missing_tasks"]),
        "plan": plan,
    }


def manual_link_report(report_id, task_ids):
    """Ручная привязка выбранных поручений."""
    from models import Task, YandexReport, YandexReportTaskLink, db

    report = YandexReport.query.get_or_404(report_id)
    executor = report.executor
    if not executor:
        return {"error": "Исполнитель не определён"}, 400

    received_at = report.received_at
    tasks_with_meta = []
    for tid in task_ids:
        task = Task.query.get(tid)
        if not task or task.executor_id != executor.id:
            continue
        if _task_linked(task):
            continue
        tasks_with_meta.append((task, "manual", 1.0))

    linked, link_records = apply_links(report, executor, tasks_with_meta, received_at)
    total_linked = YandexReportTaskLink.query.filter_by(report_id=report.id).count()
    report.items_matched = total_linked

    details = {}
    if report.match_details:
        try:
            details = json.loads(report.match_details)
        except (json.JSONDecodeError, TypeError):
            details = {}
    details.setdefault("manual", []).extend(link_records)
    report.match_details = json.dumps(details, ensure_ascii=False)

    open_total = details.get("open_total") or len(details.get("missing_tasks") or []) + total_linked
    if total_linked >= open_total and open_total > 0:
        report.completeness_status = "full"
    elif total_linked > 0:
        report.completeness_status = "partial"
    db.session.commit()
    return {"ok": True, "linked": linked, "links": link_records}, 200


def _task_linked(task):
    from models import YandexReport, YandexReportTaskLink
    if YandexReport.query.filter_by(task_id=task.id).first():
        return True
    return YandexReportTaskLink.query.filter_by(task_id=task.id).first() is not None


def get_report_preview(report_id):
    from models import YandexReport, YandexReportTaskLink, Task

    report = YandexReport.query.get_or_404(report_id)
    parsed_items = []
    parsed_sections = []
    match_details = {}
    if report.parsed_item_numbers:
        try:
            parsed_items = json.loads(report.parsed_item_numbers)
        except (json.JSONDecodeError, TypeError):
            pass
    if report.parsed_sections:
        try:
            parsed_sections = json.loads(report.parsed_sections)
        except (json.JSONDecodeError, TypeError):
            pass
    if report.match_details:
        try:
            match_details = json.loads(report.match_details)
        except (json.JSONDecodeError, TypeError):
            pass

    links = []
    for link in YandexReportTaskLink.query.filter_by(report_id=report.id).all():
        task = Task.query.get(link.task_id)
        links.append({
            "task_id": link.task_id,
            "item_number": task.item_number if task else None,
            "title": (task.title or "")[:120] if task else None,
            "method": link.match_method,
            "confidence": link.confidence,
        })

    history = []
    if report.executor_id:
        prev = YandexReport.query.filter(
            YandexReport.executor_id == report.executor_id,
            YandexReport.filename == report.filename,
            YandexReport.id != report.id,
        ).order_by(YandexReport.synced_at.desc()).limit(5).all()
        for p in prev:
            history.append({
                "id": p.id,
                "file_hash": (p.file_hash or "")[:12],
                "version": p.file_version or 1,
                "synced_at": p.synced_at.strftime('%d.%m.%Y %H:%M') if p.synced_at else None,
                "items_matched": p.items_matched or 0,
            })

    return {
        "id": report.id,
        "filename": report.filename,
        "executor": report.executor.name if report.executor else report.sender_name,
        "kchs_number": report.kchs_number,
        "parsed_items": parsed_items,
        "parsed_sections": parsed_sections,
        "items_matched": report.items_matched or 0,
        "completeness_status": report.completeness_status or "none",
        "file_version": report.file_version or 1,
        "match_details": match_details,
        "links": links,
        "history": history,
        "received_at": report.received_at.strftime('%d.%m.%Y %H:%M') if report.received_at else None,
    }


def compute_district_completeness():
    """Полнота сдачи отчётов по районам."""
    from models import Executor, Task
    from services.districts import DISTRICTS
    from services.yandex_disk import _task_has_yandex_link

    rows = []
    for name in DISTRICTS.keys():
        ex = Executor.query.filter_by(name=name).first()
        if not ex:
            rows.append({
                "name": name, "total": 0, "verified": 0, "missing": 0,
                "percentage": 0, "status": "no_tasks",
                "missing_items": [],
            })
            continue
        tasks = Task.query.filter_by(executor_id=ex.id).all()
        verified = [t for t in tasks if _task_has_yandex_link(t)]
        missing = [t for t in tasks if not _task_has_yandex_link(t)]
        total = len(tasks)
        pct = int(len(verified) / total * 100) if total else 0
        if pct >= 100 and total > 0:
            st = "full"
        elif pct > 0:
            st = "partial"
        elif total > 0:
            st = "none"
        else:
            st = "no_tasks"
        rows.append({
            "name": name,
            "total": total,
            "verified": len(verified),
            "missing": len(missing),
            "percentage": pct,
            "status": st,
            "missing_items": [
                {"item_number": t.item_number, "title": (t.title or "")[:80]}
                for t in missing[:10]
            ],
        })
    rows.sort(key=lambda x: (-x["percentage"], x["name"]))
    return rows


def auto_link_pending_reports(app, include_suggestions=True):
    """Повторная автопривязка для отчётов без связей."""
    from models import YandexReport, Executor, db
    from services.yandex_disk import YandexDiskClient, _build_response_meta, _report_needs_linking

    client = YandexDiskClient()
    files = client.list_files()
    files_by_hash = {}
    for fi in files:
        h = fi.get("md5") or fi.get("path", "")
        files_by_hash[h] = fi

    results = {"processed": 0, "linked": 0, "suggested_left": 0}
    with app.app_context():
        executors = {e.id: e for e in Executor.query.all()}
        for report in YandexReport.query.order_by(YandexReport.synced_at.desc()).all():
            if not _report_needs_linking(report):
                continue
            fi = files_by_hash.get(report.file_hash)
            if not fi:
                continue
            executor = executors.get(report.executor_id) if report.executor_id else None
            if not executor and report.sender_name:
                from services.yandex_disk import _fuzzy_match_executor
                executor = _fuzzy_match_executor(report.sender_name, list(executors.values()))
            if not executor:
                continue
            meta = _build_response_meta(report.filename, client, fi, download_pdf=True)
            r = auto_link_report(report, executor, fi, meta, include_suggestions=include_suggestions)
            results["processed"] += 1
            results["linked"] += r["linked"]
            results["suggested_left"] += r["suggest_count"]
        db.session.commit()
    return results


def get_review_queue():
    """Отчёты, требующие внимания админа: не привязаны или привязаны частично."""
    from models import YandexReport, YandexReportTaskLink

    rows = []
    for report in YandexReport.query.order_by(YandexReport.received_at.desc()).all():
        if report.superseded_by_id or report.completeness_status == "full":
            continue
        details = {}
        if report.match_details:
            try:
                details = json.loads(report.match_details)
            except (json.JSONDecodeError, TypeError):
                details = {}

        link_count = YandexReportTaskLink.query.filter_by(report_id=report.id).count()
        missing = details.get("missing_tasks") or []
        suggest = details.get("suggest") or []
        parsed_items = []
        if report.parsed_item_numbers:
            try:
                parsed_items = json.loads(report.parsed_item_numbers)
            except (json.JSONDecodeError, TypeError):
                pass

        needs_review = (
            link_count == 0
            or (report.completeness_status == "partial")
            or (parsed_items and link_count == 0)
            or (missing and report.completeness_status != "full")
        )
        if not needs_review:
            continue

        rows.append({
            "id": report.id,
            "filename": report.filename,
            "executor": report.executor.name if report.executor else report.sender_name,
            "kchs_number": report.kchs_number,
            "parsed_items": parsed_items,
            "items_matched": report.items_matched or 0,
            "link_count": link_count,
            "completeness_status": report.completeness_status or "none",
            "file_version": report.file_version or 1,
            "suggest": suggest,
            "missing_tasks": missing,
            "auto": details.get("auto") or [],
        })
    return rows


def confirm_report_suggestions(report_id, include_suggestions=True):
    """Повторная автопривязка одного отчёта (подтвердить предложения / пересканировать)."""
    from models import YandexReport, Executor, db
    from services.yandex_disk import YandexDiskClient, _build_response_meta, _fuzzy_match_executor

    report = YandexReport.query.get_or_404(report_id)
    client = YandexDiskClient()
    files = client.list_files()
    fi = None
    for f in files:
        h = f.get("md5") or f.get("path", "")
        if h == report.file_hash:
            fi = f
            break
    if not fi:
        return {"error": "Файл не найден на диске"}, 404

    executor = report.executor
    if not executor and report.sender_name:
        executor = _fuzzy_match_executor(report.sender_name, Executor.query.all())
    if not executor:
        return {"error": "Исполнитель не определён"}, 400

    meta = _build_response_meta(report.filename, client, fi, download_pdf=True)
    result = auto_link_report(report, executor, fi, meta, include_suggestions=include_suggestions)
    db.session.commit()
    return {"ok": True, **result}, 200


def notify_incomplete_after_sync(app):
    """Уведомить районы/админов о несданных пунктах после синхронизации."""
    from models import NotificationSettings, Executor
    from services.notifier import send_notification
    from services.districts import DISTRICTS

    with app.app_context():
        settings = NotificationSettings.query.first()
        if not settings or not settings.enable_email:
            logging.info("Уведомления о несданных отчётах: email выключен")
            return 0

        sent = 0
        for row in compute_district_completeness():
            if row["status"] not in ("none", "partial") or not row["missing"]:
                continue
            ex = Executor.query.filter_by(name=row["name"]).first()
            if not ex or not ex.email:
                continue
            items = ", ".join(
                f"п.{m['item_number']}" for m in row["missing_items"][:5]
            )
            subject = f"КЧС: не все отчёты сданы — {row['name']}"
            body = (
                f"Район: {row['name']}\n"
                f"Сдано: {row['verified']} из {row['total']}\n"
                f"Не хватает: {items}\n"
                f"Загрузите PDF-отчёты в папку на Яндекс.Диске."
            )
            send_notification(ex.email, subject, body)
            sent += 1
        return sent
