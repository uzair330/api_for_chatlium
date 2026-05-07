# Odoo-FastAPI Restaurant Bridge Documentation

This document provides a detailed reference for the FastAPI bridge that connects external services (like WhatsApp or web apps) to the Odoo 18.0 ERP.

---

## 🛠️ System Architecture

- **Backend**: Odoo 18.0 (Internal service `web:8069`)
- **API Bridge**: FastAPI (Internal service `api:8000`)
- **Auth**: JWT (JSON Web Tokens) with Access/Refresh cycle.
- **Protocol**: XML-RPC (Communication between FastAPI and Odoo)

---

## 🔑 Configured Credentials

For testing and local development, credentials should be configured in the `.env` file. Refer to `.env.example` for the required keys.

### 1. Odoo Admin (Back-office)
- **Login**: (See `ODOO_USER` in `.env`)
- **Password**: (See `ODOO_PASSWORD` in `.env`)
- **Purpose**: Manage Odoo directly and run seed scripts.

### 2. API Service User
- **Login**: `api_user` (Created via `create_user.py`)
- **Password**: `api_password_123`
- **Purpose**: Internal communication between FastAPI and Odoo.

### 3. Test Customer
- **Phone**: `+123456789` (Created via `seed_data.py`)
- **Purpose**: Use with `POST /customer/login` to test end-user features.

### 4. Sample Combo Product
- **Name**: `Burger & Drink Deal`
- **Logic**: Includes a choice of `Coca Cola` or `Orange Juice`.
- **Purpose**: Use to test `GET /pos/combos` and `GET /pos/combos/{id}/choices`.

## 🔐 Authentication

The system uses a dual-mode authentication system. All protected endpoints require a Bearer Token:
`Authorization: Bearer <TOKEN>`

### 1. Staff Login
Authenticates against real Odoo users (`res.users`).
- **Endpoint**: `POST /token`
- **Payload**: `{"username": "...", "password": "..."}`
- **Returns**: Access and Refresh tokens.

### 2. Customer Login
Lookup by phone number in Odoo contacts (`res.partner`).
- **Endpoint**: `POST /customer/login`
- **Payload**: `{"phone": "+123456789"}`
- **Returns**: Access and Refresh tokens.

### 3. Token Refresh
Exchange a valid refresh token for a new access token.
- **Endpoint**: `POST /refresh`
- **Headers**: `Authorization: Bearer <REFRESH_TOKEN>`

---

## 📦 POS & Ordering

### Get Categories
- **Endpoint**: `GET /pos/categories`
- **Action**: Lists all Point of Sale categories.

### Get Products
- **Endpoint**: `GET /pos/products`
- **Params**: `category_id` (Optional)
- **Action**: Lists all products available in the POS.

### Create Order
- **Endpoint**: `POST /pos/order`
- **Payload**:
  ```json
  {
    "partner_id": 123,
    "items": [
      {
        "product_id": 1, 
        "quantity": 2, 
        "note": "No onions",
        "combo_choices": [14, 22]
      }
    ]
  }
  ```
- **Prerequisite**: An active (opened) POS session must exist in Odoo.

---

## 🥗 Combo Meals & Choices (Odoo 18)

### List Combo Products
- **Endpoint**: `GET /pos/combos`
- **Action**: Returns products that have a "Combo" configuration.

### Get Combo Options
- **Endpoint**: `GET /pos/combos/{product_id}/choices`
- **Action**: Returns the selectable options for a specific combo (e.g., drinks, sides).

---

## 🏆 Loyalty & Rewards

### Check Points
- **Endpoint**: `GET /customer/loyalty`
- **Action**: Returns total points and a list of rewards the customer can redeem.

---

## 🔍 Search Endpoints

### Customer Search
- **Endpoint**: `GET /customers/search`
- **Query**: `query` (name, email, or phone)
- **Returns**: Top 20 matching contacts.

### Product Search
- **Endpoint**: `GET /products/search`
- **Query**: `query` (name or internal reference)
- **Returns**: Top 20 matching POS products.

### Order Search
- **Endpoint**: `GET /orders/search`
- **Params**: `partner_id` (optional), `reference` (optional)
- **Returns**: matching POS orders with status.

---

## 🛵 Delivery & Tracking

### Update Address
- **Endpoint**: `PUT /delivery/address`
- **Params**: `partner_id`, `address`
- **Action**: Updates the `street` field in Odoo for the contact.

### Track Order
- **Endpoint**: `GET /delivery/track/{order_id}`
- **Action**: Returns a human-friendly status (e.g., "Cooking in Kitchen", "Out for Delivery") based on Odoo's internal order state.

---

## ⚙️ Configuration & Environment

| Variable | Default | Description |
| :--- | :--- | :--- |
| `SECRET_KEY` | `super-secret...` | Used to sign JWT tokens. |
| `ODOO_URL` | `http://web:8069` | Internal address of the Odoo container. |
| `ODOO_DB` | `admin` | Target Odoo database name. |
| `ODOO_USER` | `api_user` | Dedicated Odoo user for the API bridge. |
| `ODOO_PASSWORD` | `api_password_123` | Password for the API user. |
