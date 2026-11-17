import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from dotenv import load_dotenv
from mlflow import MlflowClient
from webhook.main import write_event


load_dotenv()

TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_NAME = "sklearn-champion-worker"
WEBHOOK_EVENT = "model_version_alias.created"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def validate_config() -> None:
    if not WEBHOOK_URL or not WEBHOOK_SECRET:
        raise ValueError("Set WEBHOOK_URL and WEBHOOK_SECRET in .env")

    url = urlsplit(WEBHOOK_URL)
    if url.scheme != "https" or not url.netloc:
        raise ValueError("WEBHOOK_URL must be a reachable HTTPS URL")


def find_webhook(client: MlflowClient):
    token = None
    while True:
        page = client.list_webhooks(max_results=100, page_token=token)
        for webhook in page:
            if webhook.name == WEBHOOK_NAME:
                return webhook
        token = page.token
        if not token:
            return None


def register_webhook(client: MlflowClient):
    options = {
        "name": WEBHOOK_NAME,
        "description": "Build and tag local images for champion alias changes.",
        "url": WEBHOOK_URL,
        "events": [WEBHOOK_EVENT],
        "secret": WEBHOOK_SECRET,
        "status": "ACTIVE",
    }

    existing = find_webhook(client)
    if existing:
        return client.update_webhook(
            webhook_id=existing.webhook_id,
            **options,
        )
    return client.create_webhook(**options)


def verify_csv_writer() -> None:
    event = {
        "entity": "model_version_alias",
        "action": "created",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "name": "example_model",
            "alias": "example_alias",
            "version": "1",
        },
    }

    with TemporaryDirectory(prefix="mlflow-webhook-test-") as temp_dir:
        csv_path = Path(temp_dir) / "webhook_events.csv"
        write_event(event, csv_path)
        if not csv_path.is_file():
            raise RuntimeError("Temporary CSV writer check did not create its CSV")

    logger.info("Temporary CSV writer check succeeded")


def main() -> None:
    validate_config()
    client = MlflowClient(tracking_uri=TRACKING_URI)
    webhook = register_webhook(client)
    logger.info("Registered webhook %s at %s", webhook.name, webhook.url)
    verify_csv_writer()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Webhook registration failed")
        sys.exit(1)
