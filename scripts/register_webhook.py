import logging
import os
import sys
from urllib.parse import urlsplit

from dotenv import load_dotenv
from mlflow import MlflowClient


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
        "description": "Record MLflow alias events in the CSV event log.",
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


def main() -> None:
    validate_config()
    client = MlflowClient(tracking_uri=TRACKING_URI)
    webhook = register_webhook(client)
    logger.info("Registered webhook %s at %s", webhook.name, webhook.url)

    result = client.test_webhook(webhook.webhook_id, event=WEBHOOK_EVENT)
    if not result.success:
        raise RuntimeError(
            f"Webhook test failed ({result.response_status}): "
            f"{result.error_message}"
        )
    logger.info("Webhook test succeeded")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Webhook registration failed")
        sys.exit(1)
