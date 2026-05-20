# Odoo Restaurant POS Bridge

This service provides a secure, bi-directional bridge between **Odoo 19.0** and external applications (like WhatsApp bots or custom web apps) using FastAPI and JWT tokens.

## 🚀 Quick Start

1.  **Start the environment**:
    ```bash
    docker compose up -d
    ```
2.  **Seed test data** (Optional):
    ```bash
    uv run api/seed_data.py
    ```
3.  **Access the API**:
    The API runs on `http://localhost:8000`. You can view the interactive Swagger docs at `http://localhost:8000/docs`.

## 📖 Documentation

Detailed documentation for all authentication modes, POS operations, and search endpoints can be found in:
👉 **[DOCUMENTATION.md](./DOCUMENTATION.md)**

## 🔐 Key Features

- **Dual-Mode Auth**: Log in as Odoo Staff or as a Customer via phone lookup.
- **POS Integration**: Fetch products, categories, and place orders.
- **Advanced Search**: Fuzzy search for customers, products, and orders.
- **Delivery Tracking**: User-friendly order status mapping.

## 🛠️ Technology Stack

- **Backend**: Odoo 19.0 / PostgreSQL 15
- **Bridge**: FastAPI / Python 3.12
- **Auth**: PyJWT (Access & Refresh tokens)
- **Package Manager**: uv
