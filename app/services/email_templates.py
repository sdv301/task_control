"""HTML-шаблоны писем для районов (без ссылок на портал — только Яндекс.Диск)."""
import html
import re
from services.districts import DISTRICTS


def _esc(value):
    return html.escape(str(value or ""), quote=True)


def district_disk_url(district_name):
    """Ссылка на папку района; нечёткое совпадение по названию."""
    if not district_name:
        return None
    name = district_name.strip()
    if name in DISTRICTS:
        return DISTRICTS[name]

    normalized = re.sub(r"\s+", " ", name).lower()
    for key, url in DISTRICTS.items():
        key_l = key.lower()
        if key_l == normalized or key_l in normalized or normalized in key_l:
            return url

    # «Вилюйский район» ↔ «Вилюйский улус (район)»
    stem = normalized.split("(")[0].split("—")[0].strip()
    if len(stem) >= 5:
        for key, url in DISTRICTS.items():
            if stem in key.lower():
                return url
    return None


def _task_rows_html(rows):
    parts = []
    for label, value in rows:
        if value is None or value == "":
            continue
        parts.append(
            f'<tr>'
            f'<td style="padding:8px 12px;color:#64748b;font-size:13px;width:120px;vertical-align:top;">{_esc(label)}</td>'
            f'<td style="padding:8px 12px;color:#0f172a;font-size:14px;font-weight:500;">{_esc(value)}</td>'
            f'</tr>'
        )
    if not parts:
        return ""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
        'style="border-collapse:collapse;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin:16px 0;">'
        + "".join(parts)
        + "</table>"
    )


def _task_rows_plain(rows):
    lines = []
    for label, value in rows:
        if value is None or value == "":
            continue
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


def build_district_email_html(district_name, content_rows, note=None, badge=None):
    """Красивое HTML-письmo для района."""
    district = _esc(district_name or "муниципальное образование")
    disk_url = district_disk_url(district_name)
    support = None  # filled by caller in footer

    yandex_block = ""
    if disk_url:
        yandex_block = f"""
        <div style="text-align:center;margin:24px 0;">
          <a href="{_esc(disk_url)}" target="_blank" rel="noopener"
             style="display:inline-block;background:#fc3f1d;color:#ffffff;text-decoration:none;
                    font-size:15px;font-weight:600;padding:14px 28px;border-radius:8px;">
            Загрузить отчёт на Яндекс.Диск
          </a>
          <p style="margin:10px 0 0;font-size:12px;color:#64748b;">
            Папка вашего муниципального образования для отчётов по КЧС
          </p>
        </div>
        """
    else:
        yandex_block = """
        <p style="margin:16px 0;padding:12px;background:#fff7ed;border-left:4px solid #f59e0b;
                  color:#92400e;font-size:13px;border-radius:4px;">
          Ссылка на папку Яндекс.Диска для вашего района не найдена. Обратитесь к координатору КЧС.
        </p>
        """

    badge_html = ""
    if badge:
        badge_html = (
            f'<span style="display:inline-block;background:#dbeafe;color:#1d4ed8;'
            f'font-size:11px;font-weight:700;padding:4px 10px;border-radius:999px;'
            f'text-transform:uppercase;letter-spacing:0.04em;">{_esc(badge)}</span>'
        )

    note_html = ""
    if note:
        note_html = f'<p style="margin:12px 0 0;color:#475569;font-size:14px;line-height:1.5;">{_esc(note)}</p>'

    return f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#eef2f7;font-family:Arial,Helvetica,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
    <div style="background:linear-gradient(135deg,#1e3a8a,#2563eb);border-radius:12px 12px 0 0;padding:20px 24px;">
      <p style="margin:0;color:#bfdbfe;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;">Мониторинг КЧС</p>
      <h1 style="margin:6px 0 0;color:#ffffff;font-size:20px;font-weight:700;line-height:1.3;">
        Напоминание о сдаче отчёта
      </h1>
    </div>
    <div style="background:#ffffff;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 12px 12px;padding:24px;">
      {badge_html}
      <p style="margin:16px 0 8px;color:#0f172a;font-size:16px;line-height:1.5;">
        Уважаемые коллеги, <strong>{district}</strong>!
      </p>
      <p style="margin:0 0 8px;color:#475569;font-size:14px;line-height:1.6;">
        Просим своевременно разместить отчёт по поручению КЧС в папке вашего муниципального
        образования на <strong>Яндекс.Диске</strong>. После загрузки файл будет учтён системой мониторинга.
      </p>
      {note_html}
      {_task_rows_html(content_rows)}
      {yandex_block}
    </div>
    <div style="padding:16px 8px;text-align:center;">
      <p style="margin:0;color:#94a3b8;font-size:11px;line-height:1.6;">
        Это автоматическое письмо — не отвечайте на него.<br>
        По вопросам: <a href="mailto:{{SUPPORT_EMAIL}}" style="color:#2563eb;">{{SUPPORT_EMAIL}}</a>
      </p>
    </div>
  </div>
</body>
</html>"""


def build_district_email_plain(district_name, content_rows, note=None, support_email=""):
    district = district_name or "муниципальное образование"
    disk_url = district_disk_url(district_name)
    lines = [
        "МОНИТОРИНГ КЧС — напоминание о сдаче отчёта",
        "",
        f"Уважаемые коллеги, {district}!",
        "",
        "Просим своевременно разместить отчёт по поручению КЧС в папке вашего муниципального",
        "образования на Яндекс.Диске.",
        "",
    ]
    if note:
        lines.extend([note, ""])
    task_plain = _task_rows_plain(content_rows)
    if task_plain:
        lines.extend([task_plain, ""])
    if disk_url:
        lines.extend([
            "Папка для загрузки отчёта:",
            disk_url,
            "",
        ])
    lines.extend([
        "---",
        "Это автоматическое письмо — не отвечайте на него.",
        f"По вопросам: {support_email or '—'}",
    ])
    return "\n".join(lines)


def inject_support(html_content, support_email):
    return html_content.replace("{{SUPPORT_EMAIL}}", _esc(support_email or ""))


def task_notification_rows(task_title, item_number, deadline_str, status_line, extra=None):
    rows = [
        ("Пункт", item_number or "—"),
        ("Поручение", task_title),
        ("Срок исполнения", deadline_str),
        ("Статус", status_line),
    ]
    if extra:
        rows.append(("Примечание", extra))
    return rows
