Бот, посылающий уведомления в Telegram с помощью вебхука в Jira.

В Jira нужно создать вебхук на обновление задачи по адресу /check

Использование:
- Настроить docker-compose.yml (основной), docker-compose-main.yml (для тестов)
  - Я предпочитаю использовать Traefik для этих целей
- Выполнить __cp .env.example__ .env и заполнить .env соответственно
  - ALLOWED_KEYS - ключи, разделённые через запятую. 
  Ключ передаётся с помощью параметра skey. 
  Если ключ не найден в конфиге, доступ запрещается.
  Чтобы отключить проверку, нужно удалить строки 35-44
- Запуск:
  - npm run start - запуск docker-compose.yml
  - npm run startl - запуск docker-compose-main.yml
  - npm run serve - запуск локально
  - npm run stop - остановить docker контейнер
  - uvicorn main:app --reload - тоже запуск локально
