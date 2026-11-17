
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

EVENT_LOG_CSV = Path(
    os.getenv(
        "WEBHOOK_EVENTS_CSV",
        str(PROJECT_ROOT / "state" / "webhook_events.csv"),
    )
).expanduser().resolve()
