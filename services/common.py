
import json
import os
import time
import pika
import redis

INSTANCE = os.environ.get("HOSTNAME", "unknown")


def db():
    return redis.Redis(
        host="redis",
        port=6379,
        decode_responses=True
    )



def declare_dead_letter(channel):
    channel.exchange_declare(
        exchange="homework.dlx",
        exchange_type="direct",
        durable=True
    )
    channel.queue_declare(
        queue="homework.dlq",
        durable=True
    )
    channel.queue_bind(
        queue="homework.dlq",
        exchange="homework.dlx",
        routing_key="failed"
    )

def publish(event_type, payload, trace_id=None):
    params = pika.ConnectionParameters(
        host="rabbitmq",
        heartbeat=30,
        blocked_connection_timeout=10
    )

    for attempt in range(10):
        connection = None

        try:
            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            channel.exchange_declare(
                exchange="homework.events",
                exchange_type="fanout",
                durable=True
            )

            declare_dead_letter(channel)

            channel.queue_declare(
                queue="notification.events",
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "homework.dlx",
                    "x-dead-letter-routing-key": "failed"
                }
            )

            channel.queue_bind(
                exchange="homework.events",
                queue="notification.events"
            )

            # Очікуємо підтвердження від RabbitMQ
            channel.confirm_delivery()

            confirmed = channel.basic_publish(
                exchange="homework.events",
                routing_key="",
                body=json.dumps({
                    "type": event_type,
                    "data": payload
                }),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    headers={
                        "trace_id": trace_id or ""
                    }
                ),
                mandatory=True
            )

            if confirmed is False:
                raise RuntimeError(
                    "RabbitMQ did not confirm publication"
                )

            return

        except (
            pika.exceptions.AMQPError,
            OSError
        ):
            if attempt == 9:
                raise

            time.sleep(1)

        finally:
            if connection is not None:
                try:
                    if connection.is_open:
                        connection.close()
                except Exception:
                    pass
