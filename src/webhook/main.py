import asyncio
import base64
import csv
import hashlib
import hmac
import json
import logging
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from mlflow import MlflowClient

from webhook.config import EVENT_LOG_CSV, MLFLOW_TRACKING_URI, WEBHOOK_SECRET


logger = logging.getLogger(__name__)
csv_lock = threading.Lock()


def record_startup_champions() -> None:
    client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
    page_token = None
    snapshot_count = 0

    while True:
        models = client.search_registered_models(
            max_results=100,
            page_token=page_token,
        )
        for model in models:
            if "champion" not in model.aliases:
                continue

            champion = client.get_model_version_by_alias(model.name, "champion")
            timestamp = datetime.now(timezone.utc).isoformat()
            write_event(
                {
                    "entity": "model_version_alias",
                    "action": "startup",
                    "timestamp": timestamp,
                    "data": {
                        "name": model.name,
                        "alias": "champion",
                        "version": champion.version,
                    },
                }
            )
            snapshot_count += 1

        page_token = models.token
        if not page_token:
            break

    if snapshot_count:
        logger.info("Recorded startup snapshots for %d champion aliases", snapshot_count)
    else:
        logger.info("No champion aliases found; skipping startup snapshot")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(record_startup_champions)
    yield


app = FastAPI(title="MLflow Webhook Event Logger", lifespan=lifespan)


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


def write_event(
    payload: dict[str, object],
    output_path: Path = EVENT_LOG_CSV,
) -> str:
    written_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    event = {**payload, "written_at_utc": written_at_utc}
    with csv_lock:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        csv_data = pd.read_csv(output_path) if output_path.exists() else pd.DataFrame()
        csv_data = pd.concat([csv_data, pd.DataFrame([event])], ignore_index=True)
        csv_data.to_csv(output_path, index=False)
    return written_at_utc


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
