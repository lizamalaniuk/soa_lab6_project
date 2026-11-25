from observability import setup_observability, trace_id_var
from metrics import setup_metrics
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from common import db, INSTANCE
import requests
import json
import uuid
from datetime import datetime, timezone
from fastapi.middleware.cors import CORSMiddleware
from auth import verify_token, require_scope

app = FastAPI(title="Homework Service")

setup_observability(app, "homework")

setup_metrics(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://cad.kpi.ua"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class HomeworkIn(BaseModel):
    user_id: str
    subject: str
    description: str
    deadline: str


def save_with_outbox(task, event_type):
    """
    Атомарно зберігає домашнє завдання
    та повідомлення в Transactional Outbox.
    """
    r = db()
    event_id = str(uuid.uuid4())

    event = {
        "event_id": event_id,
        "trace_id": trace_id_var.get() or uuid.uuid4().hex,
        "type": event_type,
        "data": task,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    # Обидва записи виконуються в одній
    # атомарній транзакції Redis.
    with r.pipeline(transaction=True) as pipe:
        pipe.set(
            "homework:" + task["id"],
            json.dumps(task)
        )
        pipe.set(
            "outbox:" + event_id,
            json.dumps(event)
        )
        pipe.execute()

    return event_id


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "homework",
        "instance": INSTANCE
    }


@app.post("/homeworks", status_code=201)
def create_homework(
    item: HomeworkIn,
    token: dict = Depends(verify_token)
):
    try:
        response = requests.get(
            f"http://users:8000/users/{item.user_id}",
            headers={
                "X-Trace-ID": trace_id_var.get() or uuid.uuid4().hex
            },
            timeout=4
        )

        if response.status_code == 404:
            raise HTTPException(400, "Unknown user")

        response.raise_for_status()

    except requests.RequestException as exc:
        raise HTTPException(
            503, "User Service unavailable"
        ) from exc

    task = {
        "id": str(uuid.uuid4()),
        **item.model_dump(),
        "status": "pending"
    }

    event_id = save_with_outbox(
        task, "homework.created"
    )

    return {
        **task,
        "served_by": INSTANCE,
        "sync_user_checked": True,
        "event_id": event_id,
        "event_queued": True,
        "event_published": False
    }


@app.get("/homeworks")
def list_homeworks(
    token: dict = Depends(require_scope("homework:read"))
):
    r = db()
    keys = r.keys("homework:*")

    return {
        "items": [
            json.loads(value)
            for value in r.mget(keys)
            if value
        ] if keys else [],
        "served_by": INSTANCE
    }


@app.get("/homeworks/{task_id}")
def get_homework(
    task_id: str,
    token: dict = Depends(require_scope("homework:read"))
):
    raw = db().get("homework:" + task_id)

    if not raw:
        raise HTTPException(404, "Homework not found")

    return {
        **json.loads(raw),
        "served_by": INSTANCE
    }


@app.patch("/homeworks/{task_id}/complete")
def complete_homework(
    task_id: str,
    token: dict = Depends(verify_token)
):
    r = db()
    raw = r.get("homework:" + task_id)

    if not raw:
        raise HTTPException(404, "Homework not found")

    task = json.loads(raw)

    if task["status"] != "completed":
        task["status"] = "completed"

        event_id = save_with_outbox(
            task, "homework.completed"
        )
    else:
        event_id = None

    return {
        **task,
        "served_by": INSTANCE,
        "event_id": event_id,
        "event_queued": event_id is not None
    }
