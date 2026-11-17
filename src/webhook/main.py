import asyncio
import base64
import csv
import hashlib
import hmac
import json
import threading
import time
from datetime import datetime, timezone
import pandas as pd
from fastapi import FastAPI, HTTPException, Request

from webhook.config import EVENT_LOG_CSV, WEBHOOK_SECRET


app = FastAPI(title="MLflow Webhook Event Logger")
csv_lock = threading.Lock()


def verify_webhook(payload: bytes, request: Request) -> bool:
    signature = request.headers.get("X-MLflow-Signature", "")
    delivery_id = request.headers.get("X-MLflow-Delivery-Id", "")
    timestamp = request.headers.get("X-MLflow-Timestamp", "")
    if (
        not WEBHOOK_SECRET
        or not signature.startswith("v1,")
        or not delivery_id
    ):
        return False

    try:
        age = int(time.time()) - int(timestamp)
        payload_text = payload.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return False
    if not 0 <= age <= 300:
        return False

    signed_content = f"{delivery_id}.{timestamp}.{payload_text}"
    digest = hmac.new(
        WEBHOOK_SECRET.encode(),
        signed_content.encode(),
        hashlib.sha256,
    ).digest()
    expected = "v1," + base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


def write_event(payload: dict) -> str:
    payload["written_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with csv_lock:
        EVENT_LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
        csv_data = pd.read_csv(EVENT_LOG_CSV) if EVENT_LOG_CSV.exists() else pd.DataFrame()
        csv_data = pd.concat([csv_data, pd.DataFrame([payload])], ignore_index=True)
        csv_data.to_csv(EVENT_LOG_CSV, index=False)
    return payload["written_at_utc"]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/webhooks/mlflow")
async def mlflow_webhook(request: Request) -> dict[str, str]:
    payload = await request.body()
    if not verify_webhook(payload, request):
        raise HTTPException(401, "Invalid webhook authentication")

    try:
        payload_data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(400, "Invalid webhook JSON") from None

    timestamp = await asyncio.to_thread(write_event, payload_data)
    return {"status": "recorded", "written_at_utc": timestamp}
