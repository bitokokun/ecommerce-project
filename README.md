# E-Commerce Platform — Backend (Phase 1 MVP)

Django REST Framework backend for a multi-vendor e-commerce store.

## Live deployment
Deployed on Render as `ecommerce-backend`, connected to a Render-managed
Postgres instance. Because Render's free tier has no Shell access, the
superuser is created automatically on every boot via `start.sh`, reading
credentials from environment variables (see below) — safe to redeploy
repeatedly since it no-ops if the user already exists.

## Environment variables (set these in Render → Environment, and in your
local `.env` for the ones that apply — see `.env.example`)

| Key | Where | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | both | generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_DEBUG` | both | `True` locally, `False` on Render |
| `DJANGO_ALLOWED_HOSTS` | both | `localhost,127.0.0.1` locally, `.onrender.com` on Render |
| `POSTGRES_DB` / `USER` / `PASSWORD` / `HOST` / `PORT` | both | On Render, copy these from the Postgres service's Connections page — Render auto-generates the DB name/user (e.g. `ecommerce_klcm`), it won't be the plain `ecommerce` from your local `.env` |
| `REDIS_URL` | both | not yet used for real tasks, wired for later |
| `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | Render only | used by `start.sh` to auto-create the admin login since Shell isn't available on the free tier |

## Local setup
```bash
cp .env.example .env
docker compose up --build
```
Local dev uses `docker-compose.yml`'s own command (Django dev server with
auto-reload), not `start.sh` — `start.sh` is what Render/Docker's default
`CMD` runs (migrate → auto-superuser → gunicorn), meant for production.

- API root: http://localhost:8000/api/
- Admin: http://localhost:8000/admin/

## CORS note
`CORS_ALLOW_ALL_ORIGINS = DEBUG` alone would silently block every request
from the live frontend once `DEBUG=False` in production — fixed by also
allowing `*.onrender.com` origins explicitly in `settings.py`.

## Key endpoints
| Method | Path | Purpose |
|---|---|---|
| POST | /api/accounts/register/ | create account |
| POST | /api/auth/token/ | obtain JWT |
| GET | /api/catalog/products/ | browse/search products |
| GET | /api/catalog/products/{id}/ | product detail |
| POST | /api/catalog/products/{id}/reviews/ | leave a review |
| GET | /api/cart/ | view current cart |
| POST | /api/cart/items/ | add item to cart |
| PATCH/DELETE | /api/cart/items/{id}/ | update/remove cart line |
| POST | /api/orders/checkout/ | convert cart to order |
| GET | /api/orders/ | order history |

## Not yet built
- Payment gateway integration
- Seller dashboard beyond basic ownership checks
- Recommendation microservice (FastAPI, Phase 3)
- Celery tasks (wired up, none defined yet)
