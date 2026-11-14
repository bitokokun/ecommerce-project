# Architecture

## System overview

```mermaid
flowchart LR
    Browser["Browser<br/>React + Vite storefront"]
    subgraph Render
        Static["Static site<br/>(frontend build)"]
        API["Django REST API<br/>gunicorn in Docker"]
    end
    DB[("PostgreSQL")]
    Cloud["Cloudinary<br/>product images"]
    Turnstile["Cloudflare Turnstile"]

    Browser -->|loads app| Static
    Browser -->|"HTTPS / JSON + JWT"| API
    API --> DB
    API -->|image storage| Cloud
    API -->|verifies signup captcha| Turnstile
```

## Backend structure

```mermaid
flowchart TB
    subgraph config
        settings["settings / urls / errors"]
    end
    subgraph apps
        accounts["accounts<br/>users, addresses, seller store,<br/>auth views, token revocation"]
        catalog["catalog<br/>products, variants, images,<br/>reviews, wishlist"]
        cart["cart<br/>guest and user carts"]
        orders["orders<br/>checkout service, fulfilment,<br/>idempotency keys, stats"]
        recs["recommendations<br/>TF-IDF + co-purchase engine"]
    end
    orders --> catalog
    orders --> cart
    orders --> accounts
    cart --> catalog
    recs --> catalog
    recs --> orders
    config --> apps
```

## Data model

```mermaid
erDiagram
    USER ||--o| SELLER_PROFILE : has
    USER ||--o{ ADDRESS : saves
    USER ||--o{ PRODUCT : sells
    USER ||--o| CART : owns
    USER ||--o{ ORDER : places
    USER ||--o{ WISHLIST_ITEM : saves
    USER ||--o{ REVIEW : writes
    USER ||--o{ IDEMPOTENCY_KEY : sends
    PRODUCT ||--o{ PRODUCT_VARIANT : "sold as"
    PRODUCT ||--o{ PRODUCT_IMAGE : shows
    PRODUCT ||--o{ REVIEW : receives
    PRODUCT ||--o{ WISHLIST_ITEM : "saved in"
    CATEGORY ||--o{ PRODUCT : groups
    CART ||--o{ CART_ITEM : holds
    PRODUCT_VARIANT ||--o{ CART_ITEM : "added as"
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT_VARIANT ||--o{ ORDER_ITEM : "bought as"
    ADDRESS ||--o{ ORDER : "ships to"
    ORDER ||--o| IDEMPOTENCY_KEY : "created by"
```

`OrderItem` copies the product name, SKU and unit price when the order is placed, and carries its own fulfilment state (status, carrier, tracking number, timestamps). Each seller ships their own lines, and the order status is derived from them.

## Checkout

```mermaid
sequenceDiagram
    participant C as Client
    participant V as CheckoutView
    participant S as place_order()
    participant DB as PostgreSQL

    C->>V: POST /api/orders/checkout/ (Idempotency-Key)
    V->>V: validate payload, key format, address ownership
    V->>S: place_order(user, address, key)
    S->>DB: BEGIN
    S->>DB: INSERT idempotency key (unique per user)
    alt key already used
        DB-->>S: unique violation (waits if the first request is still running)
        S-->>V: original order
        V-->>C: 200 + Idempotent-Replayed: true
    else new key
        S->>DB: SELECT cart FOR UPDATE
        S->>DB: SELECT variants FOR UPDATE (ordered by id)
        S->>S: check product status and stock
        S->>DB: INSERT order and items, decrement stock, empty cart
        S->>DB: COMMIT
        V-->>C: 201 + order
    end
    Note over S,DB: Any failure rolls everything back, including the key,<br/>so a failed attempt can be retried with the same key.
```

Locking rules that keep this safe:

- The cart row is locked first, so two submissions from the same account serialise.
- Variant rows are always locked in ascending id order, so two carts with the same products in a different order cannot deadlock.
- Stock is checked and decremented while the rows are locked, so the last unit can only be sold once.
- The idempotency key is inserted inside the same transaction as the order. A concurrent duplicate blocks on the unique index until the first request commits, then returns the stored order.

## Authentication

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as Auth endpoints
    participant API as API

    B->>A: POST /api/auth/token/ (username, password)
    A-->>B: access token (kept in memory)<br/>refresh token (storage, or httpOnly cookie)
    B->>API: request with Bearer access token
    API-->>B: 401 when the access token expires
    B->>A: POST /api/auth/token/refresh/ (single request, shared by parallel calls)
    A-->>B: new access token + rotated refresh token
    Note over A: The previous refresh token is blacklisted on rotation
    B->>A: POST /api/auth/logout/
    A-->>B: refresh token blacklisted, cookie cleared
```

Changing the password or deleting the account blacklists every outstanding refresh token for that user.
