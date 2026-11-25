# SOA Lab 6 — Observability та автоматизоване реагування на інциденти

Навчальний проєкт із сервіс-орієнтованої архітектури (SOA). У лабораторній роботі №6 до системи мікросервісів додано збір метрик, централізовані журнали, кореляцію запитів, правила сповіщень та автоматичну реєстрацію інцидентів.

## Компоненти системи

| Компонент | Призначення |
|---|---|
| Nginx Gateway | Єдина точка входу до HTTP API |
| Users, Homework, Notifications, OAuth | Мікросервіси FastAPI |
| Redis | Зберігання даних і подій Outbox |
| RabbitMQ | Асинхронний обмін повідомленнями |
| Outbox Publisher, Consumer | Публікація та обробка подій |
| Saga Coordinator, Saga Timeout | Координація компенсацій та обробка тайм-аутів |
| Keycloak | Автентифікація та авторизація |
| A2A Producer | Додатковий агентний компонент системи |
| Prometheus | Збір і зберігання метрик |
| Grafana | Візуалізація метрик і правила сповіщень |
| Loki + Grafana Alloy | Централізований збір журналів Docker-контейнерів |
| n8n | Обробка вебхуків і реєстрація інцидентів |

## Вимоги

- Docker Desktop з підтримкою Docker Compose.
- Git (для отримання та публікації коду).
- Доступні локальні порти, які використовує проєкт (див. таблицю нижче).

## Запуск

Із кореневої папки проєкту:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d --build
```

Перевірка запущених контейнерів:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml ps
```

Перегляд журналів певного компонента:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml logs --tail=100 rabbitmq
```

Зупинка середовища:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml down
```

## Локальні адреси

| Сервіс | Адреса |
|---|---|
| API Gateway | http://localhost:8080 |
| Keycloak | http://localhost:8081 |
| A2A Producer | http://localhost:9001 |
| RabbitMQ Management | http://localhost:15672 |
| Prometheus | http://localhost:9090 |
| Prometheus Targets | http://localhost:9090/targets |
| Grafana | http://localhost:3000 |
| Loki | http://localhost:3100 |
| n8n | http://localhost:5678 |

Параметри входу в інтерфейси визначаються конфігураціями відповідних сервісів. Паролі й токени не слід публікувати в репозиторії; для використання поза локальним навчальним середовищем замініть тестові облікові дані та налаштуйте захищений доступ.

## Що реалізовано у лабораторній №6

### Метрики Prometheus

Для чотирьох FastAPI-сервісів (`users`, `homework`, `notifications`, `oauth`) налаштовано HTTP-метрики. У Prometheus також відстежуються сам Prometheus, RabbitMQ і Saga Coordinator. У перевіреному середовищі всі **7 цілей** мали статус `UP`.

У Grafana створено дашборд **SOA Lab 6 — Observability Dashboard** з панелями:

- доступність мікросервісів;
- інтенсивність HTTP-запитів та відсоток помилок;
- затримки HTTP (p50, p95, p99);
- кількість повідомлень у чергах RabbitMQ та доступність брокера;
- метрики обробки повідомлень Saga Coordinator.

### Журнали та Trace ID

Сервіси формують структуровані журнали, які збирає Alloy та передає до Loki. Для HTTP-запитів використовується заголовок `X-Trace-ID`. Ідентифікатор також передається між компонентами асинхронного маршруту через RabbitMQ, що допомагає зіставляти записи різних сервісів.

Це **кореляція за Trace ID**, а не повноцінний розподілений трейсинг зі span-ами через OpenTelemetry.

Приклад фільтра в Grafana Explore (Loki):

```logql
{service="users"} |= "lab6-loki-test-456"
```

### Сповіщення та n8n

У Grafana налаштовано правила **SOA - Service Down** та **SOA - High Latency p99**. Сповіщення надходять у n8n через webhook `/webhook/soa-incident`, після чого інформація про інцидент записується до Data Table `soa_incidents`.

Під час перевірки зупинка `notifications` спричинила спрацьовування сповіщення й появу нового запису про інцидент у n8n.

### Saga та RabbitMQ

Saga Coordinator обробляє повідомлення з `homework.dlq` і реалізує компенсаційний сценарій. Відповідні метрики експортуються з компонента до Prometheus. Для RabbitMQ постійно увімкнені плагіни `rabbitmq_management` і `rabbitmq_prometheus` через файл `rabbitmq/enabled_plugins`.

Перевірка черг:

```bash
docker compose exec rabbitmq rabbitmqctl list_queues name messages consumers
```

Перевірка активних плагінів:

```bash
docker compose exec rabbitmq rabbitmq-plugins list -e
```

## Структура важливих файлів

```text
soa_lab6_project/
├── docker-compose.yml
├── docker-compose.monitoring.yml
├── rabbitmq/
│   └── enabled_plugins
├── monitoring/
│   ├── config.alloy
│   ├── loki.yml
│   └── prometheus.yml
└── services/
    ├── observability.py
    ├── metrics.py
    ├── coordinator_metrics.py
    ├── common.py
    ├── consumer.py
    ├── outbox_publisher.py
    ├── saga_coordinator.py
    └── ...
```

## Перенесення конфігурації Grafana та n8n

Дашборди й правила Grafana, а також workflow та Data Table n8n, створені через вебінтерфейс, **не обов'язково містяться у вихідному коді**. Перед перенесенням лабораторної на інший комп'ютер потрібно окремо експортувати або налаштувати їхнє автоматичне створення. Запуск контейнерів сам по собі не гарантує відновлення всіх цих об'єктів.

## Обмеження

- Реплікація, шардинг та метрики `replication lag` не заявляються як реалізовані без окремого розгортання й тестування відповідних механізмів.
- Налаштування та облікові дані навчального середовища не призначені для публічного продакшн-розгортання.
- Фактичний стан системи перевіряйте за Docker Compose, Prometheus Targets і журналами контейнерів.

## Результат

У лабораторній роботі створено базову систему спостережуваності для SOA: метрики, журнали, ідентифікатори кореляції, моніторинг черг, виявлення проблем і автоматичну фіксацію інцидентів.
