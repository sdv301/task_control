# Email-уведомления task-app (SMTP)

Портал отправляет письма через SMTP. Настройки — в `.env`, передаются в контейнер `task-app`.

## Рекомендуемая схема (Mail.ru + контакт @sakha.gov.ru)

**Отправка** — через ящик **@mail.ru** (пароль «для внешних приложений»).  
**Контакт в тексте письма** — отдельный адрес (`SMTP_SUPPORT_EMAIL`), например `shahtarin.dd@sakha.gov.ru` — только в подписи и Reply-To, не для SMTP-логина.

```env
SMTP_SERVER=smtp.mail.ru
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=portal@mail.ru
SMTP_PASSWORD=<пароль для внешних приложений>
SMTP_FROM=portal@mail.ru
SMTP_FROM_NAME=No Reply
SMTP_SUPPORT_EMAIL=shahtarin.dd@sakha.gov.ru
```

В письме будет: «…напишите на **shahtarin.dd@sakha.gov.ru**», а отправитель — **No Reply \<portal@mail.ru\>**.

## Переменные окружения

| Переменная | Пример | Описание |
|------------|--------|----------|
| `SMTP_SERVER` | `smtp.mail.ru` | Хост SMTP |
| `SMTP_PORT` | `587` | 587 — STARTTLS, 465 — SSL |
| `SMTP_USER` | `portal@mail.ru` | Логин Mail.ru |
| `SMTP_PASSWORD` | `***` | Пароль для внешних приложений |
| `SMTP_FROM` | `portal@mail.ru` | Envelope-отправитель |
| `SMTP_FROM_NAME` | `No Reply` | Имя в поле From |
| `SMTP_SUPPORT_EMAIL` | `shahtarin.dd@sakha.gov.ru` | Контакт в подписи и Reply-To |
| `SMTP_CONTACT_URL` | `https://…` | Ссылка на контакты (необязательно) |
| `SMTP_USE_TLS` | `true` | STARTTLS на 587 |
| `SMTP_USE_SSL` | `false` | SSL на 465 |

## Mail.ru — пошагово

1. Войти в [mail.ru](https://mail.ru) → **Настройки** → **Безопасность**.
2. Создать **«Пароль для внешних приложений»** (обычный пароль входа для SMTP не подходит).
3. В `.env` указать `SMTP_USER` / `SMTP_FROM` = полный адрес `@mail.ru`.
4. Пересоздать контейнер:  
   `docker compose --env-file .env up -d --force-recreate task-app`
5. `/task/admin/settings` → тестовое письмо.

Альтернатива для Mail.ru: порт **465**, `SMTP_USE_SSL=true`, `SMTP_USE_TLS=false`.

## Проверка и рассылка

- **Тестовое письмо** — админка task-app.
- **Автоуведомления** — «Запустить проверку сейчас» (сроки, просрочка).
- **Сводка просроченных** — отдельная кнопка в админке.

### Cron (ежедневно 08:00)

```bash
0 8 * * * cd ~/my-portal && docker compose --env-file .env exec -T task-app python -m services.notifier
```

## Безопасность

- Не коммитьте `.env` с паролями.
- `SMTP_SUPPORT_EMAIL` может быть любым рабочим адресом для ответов — не обязан совпадать с `SMTP_FROM`.
