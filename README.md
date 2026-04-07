# AlertsRouter

A FastAPI service that routes incoming alerts to the right destination based on configurable rules. Submit an alert, and the router evaluates it against your routing configs — matching by severity, service, group, or labels — and dispatches it to Slack, Email, PagerDuty, or a Webhook.

## Features

- Priority-based alert routing (higher priority wins when multiple rules match)
- Suppression windows to silence duplicate alerts from the same service within a time window
- Dry-run mode to test routing logic without persisting any state
- Route targets: Slack, Email, PagerDuty, Webhook
- Glob pattern matching on service names (e.g. `payment-*` matches `payment-api`)
- System-wide statistics by severity, route, and service
- Full async stack with PostgreSQL

## Tech Stack

- **FastAPI** -- API Server (type-safe, async, OpenAPI docs, high performance)
- **SQLAlchemy (async)** + **asyncpg** — async ORM and PostgreSQL driver
- **Pydantic** + **pydantic-settings** — schema validation and env config
- **Alembic** — database migrations
- **Uvicorn** — ASGI server
- **pytest** - Unit tests with SQLite for database
- **Database** - Postgress
- **Docker** - Containerization


## How to build and run the project
Checkout the project gh repo clone kotla-satya/AlertsRouter
The service is available at after getting the docker up . `http://localhost:8080`.

## Docker

Build and run with Docker Compose (recommended — includes PostgreSQL, no local setup needed):

```bash
docker compose build
docker compose up -d
```

The first run builds the image, starts PostgreSQL, waits for it to be ready, runs Alembic
migrations, then starts the server. Data persists across restarts via a named Docker volume.

```bash
# Stop containers (data volume is kept)
docker compose down

# Stop and wipe all data
docker compose down -v
```

## Interactive API Docs

FastAPI auto-generates interactive documentation — no extra setup needed:

- **Swagger UI**: `http://localhost:8080/docs`

![img.png](img.png)

## API Reference

### Routes

Manage routing configurations that determine where alerts are sent.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/routes` | Create or update a routing config |
| `GET` | `/routes` | List all routing configs |
| `DELETE` | `/routes/{id}` | Delete a routing config |

**Create a route:**
```bash
curl -X POST http://localhost:8080/routes \
  -H "Content-Type: application/json" \
  -d '{
    "id": "route-critical-slack",
    "conditions": {
      "severity": ["critical"],
      "service": ["payment-*"]
    },
    "target": {
      "type": "slack",
      "channel": "#alerts-critical"
    },
    "priority": 10,
    "suppression_window_seconds": 300
  }'
```

**List all routes:**
```bash
curl http://localhost:8080/routes
```

**Delete a route:**
```bash
curl -X DELETE http://localhost:8080/routes/route-critical-slack
```

---

### Alerts

Submit alerts for routing and query past results.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/alerts` | Submit an alert for routing |
| `GET` | `/alerts/{id}` | Get routing result for a specific alert |
| `GET` | `/alerts` | List alerts, with optional filters |

**Submit an alert:**
```bash
curl -X POST http://localhost:8080/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "id": "alert-001",
    "severity": "critical",
    "service": "payment-api",
    "group": "backend",
    "description": "Payment service is returning 500s",
    "timestamp": "2026-04-06T10:00:00Z",
    "labels": {"env": "production", "region": "us-east-1"}
  }'
```

**Get alert by ID:**
```bash
curl http://localhost:8080/alerts/alert-001
```

**Filter alerts by query params** (all optional):
```bash
curl "http://localhost:8080/alerts?service=payment-api&severity=critical&routed=true&suppressed=false"
```

---

### Dry Run

Test routing logic without persisting any state. Same request/response format as `POST /alerts`.

```bash
curl -X POST http://localhost:8080/test \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-alert",
    "severity": "warning",
    "service": "user-service",
    "group": "backend",
    "timestamp": "2026-04-06T10:00:00Z"
  }'
```

---

### Stats

Get system-wide routing statistics.

```bash
curl http://localhost:8080/stats
```

Response includes totals by severity, by route, and by service.

---

### Reset

Clear all data from the database (alerts, routing configs, suppressions).

```bash
curl -X POST http://localhost:8080/reset
# Response: {"status": "ok"}
```

## Authentication

This service has no authentication. All endpoints are open. If you expose it outside a trusted network, put it behind an API gateway or reverse proxy that handles auth.

## Logs

The service logs every HTTP request and response to stdout using Python's standard `logging` module at `INFO` level. Format:

```
2026-04-06 10:00:00,123 INFO alerts_router: → POST /alerts
2026-04-06 10:00:00,145 INFO alerts_router: ← 200 POST /alerts (21.4ms)
```

**Local:**
Logs print directly to your terminal when running with `uvicorn`.

**Docker:**
```bash
# Tail logs from a running container
docker logs -f <container_id>

# Or find container ID first
docker ps
docker logs -f alertsrouter-app-1
```



## Local Setup

## Prerequisites

- Python 3.12+
- PostgreSQL (running and accessible)


```bash
# 1. Clone and install dependencies
git clone <repo-url>
cd AlertsRouter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env .env.local
# Edit .env.local and set DATABASE_URL to your local PostgreSQL instance

# 3. Run database migrations
alembic upgrade head

```

## Project Structure

```
AlertsRouter/
├── app/
│   ├── main.py          # FastAPI app, middleware, exception handlers
│   ├── config.py        # Pydantic settings (loads from .env / .env.local)
│   ├── database.py      # Async engine, session, Base class
│   ├── models/          # SQLAlchemy ORM models
│   ├── schemas/         # Pydantic request/response schemas
│   ├── repositories/    # Database access layer
│   ├── services/        # Business logic
│   └── routers/         # API endpoint handlers
├── alembic/             # DB Migration scripts
├── tests/               # pytest test suite
├── docs/                # Design documentation
├── Dockerfile
├── alembic.ini
├── requirements.txt
├── .env                 # Default config (committed)
└── .env.local           # Local overrides (gitignored)
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | `postgresql+asyncpg://postgres:password@localhost:5432/alerts_router` | PostgreSQL async connection string |

Set values in `.env.local` for local development (gitignored). `.env` contains the defaults and is committed to the repo.


## Database Migrations/Schema Changes

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "describe your change"

# Roll back one migration
alembic downgrade -1

# Check current revision
alembic current
```


## Running Tests
Tests use an in-memory SQLite database via `aiosqlite` — no PostgreSQL required. Each test gets a fresh database via the fixtures in `tests/conftest.py`.

Go to the project root, install dependencies by running `pip install -r requirements-test.txt`

```bash
# Run all tests
python -m pytest -v
```


**Log level:**
The default level is `INFO`. To increase verbosity (e.g. see SQLAlchemy queries), set `PYTHONPATH` or adjust the level in `app/main.py`:
```python
logging.basicConfig(level=logging.DEBUG, ...)
```