# Real Estate & Property API v1.0

This API is designed for Property Dealers and Real Estate agencies, integrated with **Odoo 19.0**.

---

## 🔐 Authentication

Uses JWT with Access (60m) and Refresh (7d) tokens.

### `POST /token`
**Login** — Authenticate agents using Odoo credentials.

### `POST /refresh`
**Refresh** — Renew your session.

---

## 🏠 Property Management

### `GET /properties`
List all properties (Houses, Flats, Plots).
- `skip`: Pagination offset.
- `limit`: Records per page.

### `POST /properties` (Protected)
Add a new property listing.
**Request Body:**
```json
{
  "name": "Luxury Ocean View Villa",
  "price": 45000000,
  "property_type": "House",
  "bedrooms": 5,
  "bathrooms": 4,
  "area_sqft": 4500,
  "location": "Karachi"
}
```

---

## 📞 Leads & Inquiries

### `GET /inquiries` (Protected)
View all customer inquiries (CRM Leads).

### `POST /inquiries` (Public)
Submit a customer inquiry for a property.
**Request Body:**
```json
{
  "customer_name": "John Doe",
  "customer_phone": "+923001234567",
  "property_id": 45,
  "message": "Interested in viewing this property next Sunday."
}
```

---

## 📊 Analytics

### `GET /dashboard/stats` (Protected)
Get real-time stats on Properties, Active Inquiries, and Registered Agents.

---

## 🚀 Deployment
The API runs on port **8003**.
Documentation available at `http://localhost:8003/docs`.
