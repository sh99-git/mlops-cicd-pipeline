# MLflow webhook event logger

This FastAPI service receives MLflow model-version alias webhook events,
authenticates them, and appends the original JSON payload to a CSV file with
the UTC time it was written. It does not download or serve models.

## Configure

Create a `.env` file:

```env
MLFLOW_TRACKING_URI=http://127.0.0.1:5000
WEBHOOK_URL=https://your-public-host/webhooks/mlflow
WEBHOOK_SECRET=your-shared-webhook-secret
# Generate once with the command below; keep this value stable across restarts.
MLFLOW_WEBHOOK_SECRET_ENCRYPTION_KEY=<generated-fernet-key>
# Optional; defaults to state/webhook_events.csv
WEBHOOK_EVENTS_CSV=state/webhook_events.csv
```

Generate the MLflow encryption key once:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep the key private and do not commit `.env`. MLflow uses this key to encrypt
webhook secrets in its backend database. If the key is unset, MLflow generates
an ephemeral key; changing or losing the key makes previously stored webhook
secrets unreadable and can cause the webhook list API to return HTTP 500.

MLflow requires the webhook destination to use HTTPS and be reachable by the
MLflow server. For local development, expose the FastAPI endpoint through an
HTTPS tunnel or reverse proxy.

## Run

Start the MLflow server:

```bash
uv run --env-file .env mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --host 127.0.0.1 \
  --port 5000
```

Use `uv run --env-file .env mlflow ui` if starting the UI instead.

Start the webhook receiver in another terminal:

```bash
uv run uvicorn webhook.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1
```

Register the alias-change webhook with MLflow:

```bash
uv run python scripts/register_webhook.py
```

The registration script creates or updates a webhook for
`model_version_alias.created` and checks the CSV writer using a temporary file
that is deleted immediately afterward. It does not send a test webhook, so the
check does not add example events to the persistent log. Events are accepted at
`POST /webhooks/mlflow`; `GET /health` is available for a health check.

## Event log

By default, accepted webhook events and startup snapshots are appended to
`state/webhook_events.csv`:

```csv
entity,action,timestamp,data,written_at_utc
model_version_alias,startup,2026-11-17T10:22:05+00:00,"{'name': 'property-rate', 'alias': 'champion', 'version': '4'}",2026-11-17T10:22:05Z
```

`timestamp` is the MLflow event time for webhook deliveries and the snapshot
time for startup rows; `written_at_utc` is when this service writes the row.
The nested `data` mapping is rendered by pandas in the CSV cell. Set
`WEBHOOK_EVENTS_CSV` to change the output path. Invalid, expired, or
unauthenticated webhook requests are not written.

At startup, the service searches registered models for the `champion` alias.
For each alias that resolves to a registered model version, it writes a row
with `action=startup` to record the initial state. If none are found, it skips
the snapshot. This records registry metadata; it does not download model
artifacts.
