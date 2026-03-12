# KipFP — Financial Planning & Consolidation

Full-stack platform for the Kip Group of Companies: financial planning,
consolidation, and reporting across 10+ Australian entities.
June 30 financial year end. All amounts in AUD.

## Stack

| Layer    | Technology                                                  |
| -------- | ----------------------------------------------------------- |
| Backend  | FastAPI, SQLAlchemy 2.0 (async), Alembic, Celery, asyncpg   |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, Zustand |
| Database | PostgreSQL 15                                                |
| Cache    | Redis 7                                                      |

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> kipfp && cd kipfp

# 2. Create your environment file
cp .env.example .env
# Edit .env and fill in any required credentials (SECRET_KEY at minimum)

# 3. Start all services
docker compose up --build

# 4. Run database migrations (first time only — in a second terminal)
docker compose exec backend alembic upgrade head

# 5. (Optional) Create an admin user
docker compose exec backend python -m app.scripts.seed_admin
```

Once running, visit:

| Service        | URL                        |
| -------------- | -------------------------- |
| Frontend       | http://localhost:3000       |
| Backend API    | http://localhost:8000       |
| API Docs       | http://localhost:8000/docs  |
| Celery Flower  | http://localhost:5555       |

## Project Structure

```
kipfp/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers
│   │   ├── core/           # Config, auth, dependencies
│   │   ├── db/             # SQLAlchemy engine, models
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # Business logic
│   │   ├── connectors/     # NetSuite & Xero API clients
│   │   ├── scripts/        # CLI utilities (seed, etc.)
│   │   ├── worker.py       # Celery app
│   │   └── main.py         # FastAPI app entry point
│   ├── alembic/            # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/ui/  # shadcn/ui components
│   │   ├── pages/          # Login, Dashboard
│   │   ├── stores/         # Zustand state
│   │   ├── utils/          # Axios instance
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## API Endpoints (Phase 1)

| Method | Path                    | Description            |
| ------ | ----------------------- | ---------------------- |
| GET    | `/api/v1/health`        | Health check           |
| POST   | `/api/v1/auth/login`    | Obtain access token    |
| POST   | `/api/v1/auth/refresh`  | Refresh access token   |

## Roles

| Role    | Description                        |
| ------- | ---------------------------------- |
| admin   | Full access                        |
| finance | Read/write financial data          |
| viewer  | Read-only access                   |

## Development

```bash
# Run backend tests
docker compose exec backend pytest

# Create a new migration
docker compose exec backend alembic revision --autogenerate -m "description"

# Apply migrations
docker compose exec backend alembic upgrade head
```
