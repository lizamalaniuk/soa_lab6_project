
import json
import os
import time
import pika
import redis

from common import db, declare_dead_letter
from observability import logger, trace_id_var

# Керуємо тестовою помилкою через змінну середовища.
SIMULATE_FAILURE = os.getenv("SIMULATE_FAILURE", "false").lower() == "true"


def process_event(event):
    event_type = event["type"]
    data = event["data"]
    event_id = data.get("event_id")

    if event_type != "homework.created":
        return

    if not event_id:
        raise ValueError("Missing event_id")

    if SIMULATE_FAILURE:
        raise RuntimeError("Simulated consumer failure for SAGA")

    r = db()
    task_key = "homework:" + data["id"]
    processed_key = "inbox:" + event_id

    while True:
        try:
            with r.pipeline() as pipe:
                pipe.watch(task_key, processed_key)

                if pipe.exists(processed_key):
                    print("DUPLICATE EVENT:", event_id, flush=True)
                    return

                raw = pipe.get(task_key)
                if not raw:
                    raise ValueError("Homework not found")

                task = json.loads(raw)

                if task["status"] == "cancelled":
                    print("ALREADY CANCELLED:", data["id"], flush=True)
                    return

                if task["status"] != "pending":
                    print("UNEXPECTED STATUS:", task["status"], flush=True)
                    return

                task["status"] = "confirmed"

                message = {
                    "event": event_type,
                    "homework_id": data["id"],
                    "user_id": data["user_id"],
                    "message": "Завдання створено: " + data["subject"]
                }

                pipe.multi()
                pipe.set(task_key, json.dumps(task))
                pipe.set(processed_key, "processed")
                pipe.lpush(
                    "notifications",
                    json.dumps(message, ensure_ascii=False)
                )
                pipe.execute()

                print("SAGA CONFIRMED:", data["id"], flush=True)
                return

        except redis.WatchError:
            continue


def main():
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host="rabbitmq", heartbeat=30)
            )
            ch = connection.channel()

            ch.exchange_declare(
                exchange="homework.events",
                exchange_type="fanout",
                durable=True
            )

            declare_dead_letter(ch)

            ch.queue_declare(
                queue="notification.events",
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "homework.dlx",
                    "x-dead-letter-routing-key": "failed"
                }
            )

            ch.queue_bind(
                exchange="homework.events",
                queue="notification.events"
            )

            def callback(channel, method, properties, body):
                headers = properties.headers or {}
                trace_id = headers.get("trace_id") or "unknown"

                token = trace_id_var.set(trace_id)
                started = time.perf_counter()

                try:
                    event = json.loads(body)

                    logger.info(json.dumps({
                        "event": "message_received",
                        "service": "consumer",
                        "trace_id": trace_id,
                        "event_type": event.get("type"),
                        "event_id": event.get("data", {}).get("event_id")
                    }))

                    process_event(event)
                    channel.basic_ack(delivery_tag=method.delivery_tag)

                    logger.info(json.dumps({
                        "event": "message_processed",
                        "service": "consumer",
                        "trace_id": trace_id,
                        "status": "success",
                        "duration_ms": round(
                            (time.perf_counter() - started) * 1000, 2
                        )
                    }))

                except Exception as exc:
                    logger.error(json.dumps({
                        "event": "message_failed",
                        "service": "consumer",
                        "trace_id": trace_id,
                        "status": "error",
                        "error_type": type(exc).__name__
                    }))

                    channel.basic_nack(
                        delivery_tag=method.delivery_tag,
                        requeue=False
                    )

                finally:
                    trace_id_var.reset(token)

            ch.basic_qos(prefetch_count=1)
            ch.basic_consume(
                queue="notification.events",
                on_message_callback=callback
            )

            print("Consumer started; failure mode:", SIMULATE_FAILURE, flush=True)
            ch.start_consuming()

        except Exception as exc:
            print("Consumer reconnect:", str(exc), flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
