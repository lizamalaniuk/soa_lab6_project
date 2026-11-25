
import json
import time
from common import db, publish


def process_outbox():
    r = db()

    for key in r.scan_iter("outbox:*"):
        raw = r.get(key)

        if not raw:
            continue

        event = json.loads(raw)

        if event.get("status") != "pending":
            continue

        try:
            publish(
                event["type"],
                {
                    **event["data"],
                    "event_id": event["event_id"]
                },
                trace_id=event.get("trace_id")
            )

            event["status"] = "published"
            r.set(key, json.dumps(event))

            print(
                f"OUTBOX PUBLISHED: {event['event_id']}",
                flush=True
            )

        except Exception as exc:
            print(
                f"OUTBOX ERROR: {exc}",
                flush=True
            )


if __name__ == "__main__":
    print("Outbox Publisher started", flush=True)

    while True:
        try:
            process_outbox()
        except Exception as exc:
            print(f"Publisher error: {exc}", flush=True)

        time.sleep(2)
