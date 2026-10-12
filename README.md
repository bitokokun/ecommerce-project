# Souk — multi-vendor e-commerce marketplace

A full-stack marketplace in the style of Amazon / Digikala: shoppers browse and buy,
sellers list and manage their own products. Django REST API + React storefront, deployed live.

**Live demo:** https://ecommerce-frontend-7q36.onrender.com
**API:** https://ecommerce-backend-quog.onrender.com/api/catalog/products/
**Frontend repo:** https://github.com/bitokokun/ecommerce-frontend

> Hosted on free tiers, so the first request after a quiet period can take up to a minute while the server wakes up.

## What it does

**Shoppers**
- Browse and search products, filter by 30 categories, pick a variant (size/colour/SKU)
- Cart for guests and for logged-in users
- Checkout with a saved shipping address (country chosen from a list of 196)
- Order history

**Sellers**
- Register as a seller, then manage listings from a dashboard (no Django admin needed)
- Create products, add variants and stock, upload photos
- See orders that include their products, with where to ship them, and get an in-app alert when a new one arrives

**Protection against abuse**
- Rate limiting on signup, product writes and image uploads
- Uploaded images are actually decoded and checked (type and size), not trusted by file name
- Cloudflare Turnstile captcha on signup, verified on the server
- Role checks on the server: only seller accounts can create products, and nobody can sign up as admin

## Stack

| Layer | Technology |
|---|---|
| API | Django 5, Django REST Framework, JWT (SimpleJWT) |
| Database | PostgreSQL |
| Frontend | React 18, React Router, Vite |
| Images | Cloudinary |
| Packaging / hosting | Docker, Render, WhiteNoise for static files |

```
React storefront  ──HTTPS/JSON──▶  Django REST API  ──▶  PostgreSQL
 (Render static)                    (Docker on Render)  └─▶ Cloudinary (images)
```

## Design decisions worth knowing

- **Variants are the stocked unit.** `ProductVariant` (SKU, price override, stock) is what gets bought, so sizes and colours don't need a schema change later.
- **Checkout can't oversell.** It runs in one transaction and locks the variant rows with `select_for_update()`, re-checks stock, then decrements it. Two buyers racing for the last unit can't both succeed.
- **Orders keep their history.** `OrderItem` copies the product name, SKU and price at purchase time, so later edits or deletions don't rewrite past orders.
- **Guest and account carts.** Guests are tracked by session; logging in switches to the account's cart.
- **Seller alerts need no extra table.** "New orders" is computed from existing orders since the seller last looked.
- **Images live on Cloudinary** because Render's disk is wiped on every redeploy.
- **One source of truth for countries.** The server owns the list; the dropdown fetches it and the address serializer validates against it.

## API overview

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/accounts/register/` | Create an account (customer or seller) |
| POST | `/api/auth/token/` | Log in, get JWT |
| GET | `/api/accounts/countries/` | Countries for the address dropdown |
| GET/POST | `/api/accounts/addresses/` | Own shipping addresses |
| GET | `/api/catalog/products/` | Public product list (search, filter, ordering) |
| GET | `/api/catalog/products/{id}/` | Product detail with variants and images |
| GET | `/api/catalog/categories/` | All categories |
| GET | `/api/catalog/products/mine/` | A seller's own products, drafts included |
| POST | `/api/catalog/products/` | Create product (seller accounts only) |
| POST | `/api/catalog/products/{id}/variants/` | Add a variant |
| POST | `/api/catalog/products/{id}/images/upload/` | Upload a photo |
| GET/POST | `/api/cart/`, `/api/cart/items/` | Cart |
| POST | `/api/orders/checkout/` | Turn the cart into an order |
| GET | `/api/orders/` | Own order history |
| GET | `/api/orders/received/` | Orders containing the seller's products |

## Run it locally

```bash
cp .env.example .env        # on Windows cmd: copy .env.example .env
docker compose up --build
```

API at http://localhost:8000/api/ and admin at http://localhost:8000/admin/.
Create an admin with `docker compose exec web python manage.py createsuperuser`.
The React app is in the [frontend repo](https://github.com/bitokokun/ecommerce-frontend).

### Environment variables

| Name | Purpose |
|---|---|
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Django basics |
| `POSTGRES_DB` / `USER` / `PASSWORD` / `HOST` / `PORT` | Database connection |
| `CLOUDINARY_URL` | Image storage (optional locally; uploads use local disk without it) |
| `TURNSTILE_SECRET_KEY` | Captcha check (optional; skipped when unset) |
| `DJANGO_SUPERUSER_USERNAME` / `EMAIL` / `PASSWORD` | Auto-creates the admin on deploy |

## Not built yet

- Payment gateway (checkout currently creates a pending order)
- Moderation step before a seller's product goes live
- Email notifications (alerts are in-app only)
- Automated tests
