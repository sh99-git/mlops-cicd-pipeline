
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")

EVENT_LOG_CSV = Path(
    os.getenv(
        "WEBHOOK_EVENTS_CSV",
        str(PROJECT_ROOT / "state" / "webhook_events.csv"),
    )
).expanduser().resolve()
