# QueueLess

> Your Time Matters. Not Your Waiting.

QueueLess is an open-source digital queue platform for clinics, salons, service centers and other walk-in businesses in India. Customers scan a QR code, take a digital token, and watch their live position and estimated wait without installing an app. Staff manage counters and customers from a business-scoped API.

Author: Aniket Talan · License: MIT

## Status

This is an early core build. The queue engine and REST API are implemented and tested. The web frontend, WebSocket updates, Docker setup and CI are not built yet.

### Implemented
- Business registration with a one-time API key (only its SHA-256 hash is stored)
- Services, queues, and multiple counters per queue
- Customer join, token status, and cancellation through unguessable codes (the QR target)
- Fair FIFO ordering by token number, with hold, resume, complete, no-show and cancel
- Atomic token numbering and queue advancement, serialised per queue
- Position and ETA from historical service durations, falling back to the configured average
- Append-only queue event history
- Business-scoped authorization on every staff route

### Not yet built
Frontend and PWA, WebSocket live updates, Hindi/English UI, password login with JWT, rate limiting, business audit log, operating-hours ETA, analytics, Alembic migrations, Docker and CI, public display screen.

## Quick start (backend)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive API reference.

## API overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/businesses` | none | Register a business; returns `api_key` once |
| POST | `/api/services` | API key | Create a service |
| POST | `/api/queues` | API key | Create a queue for a service |
| POST | `/api/queues/{id}/counters` | API key | Add a counter |
| GET | `/api/queues/{id}/board` | API key | Waiting, held and called tokens |
| POST | `/api/queues/{id}/next` | API key | Call the next customer to a counter |
| POST | `/api/tokens/{id}/{hold,resume,complete,no_show,cancel}` | API key | Staff token actions |
| GET | `/api/public/queues/{code}` | none | Queue status (now serving, waiting, ETA) |
| POST | `/api/public/queues/{code}/join` | none | Take a token |
| GET | `/api/public/tokens/{code}` | none | Token position and status |
| POST | `/api/public/tokens/{code}/cancel` | none | Cancel a waiting token |

Staff routes send the key in the `X-API-Key` header.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./queueless.db` | Any SQLAlchemy URL. PostgreSQL uses `postgresql+psycopg://…` |

## Tests

```bash
cd backend && pytest
```

Tests always run against `sqlite:///./test_queueless.db`, regardless of `DATABASE_URL`, so they never touch a real database. The concurrency test issues 20 tokens from parallel threads and checks that numbers are unique and gapless. The suite does not yet exercise PostgreSQL row locks directly.

## Contributing

Issues and pull requests are welcome. Keep changes covered by tests, and keep queue rules in `app/engine.py` so they stay independent of HTTP.

## License

MIT. Copyright (c) 2026 Aniket Talan. See [LICENSE](LICENSE).
