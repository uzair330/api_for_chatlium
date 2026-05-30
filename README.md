# Chatlium Odoo API Stack

This project runs **Odoo 19.0** as a backend with four independent FastAPI microservices that act as a 100% Odoo-native proxy layer. All authentication, authorization, and business logic is handled directly by the Odoo backend.

| Service | Local URL | Swagger Docs |
| --- | --- | --- |
| 🍽️ Restaurant API | `http://localhost:8000` | `http://localhost:8000/docs` |
| 🏫 School API | `http://localhost:8001` | `http://localhost:8001/docs` |
| 🏥 Hospital API | `http://localhost:8002` | `http://localhost:8002/docs` |
| 🏠 Real Estate API | `http://localhost:8003` | `http://localhost:8003/docs` |
| ⚙️ Odoo UI | `http://localhost:8069` | Odoo web interface |

---

## 🛡️ Authentication (Odoo Native Session)

All 4 APIs use **Odoo's native JSON-RPC session authentication**. There are no custom JWTs — Odoo itself issues and validates every session, enforcing its built-in RBAC and Record Rules automatically.

### Admin / Staff Login
```http
POST /login
Content-Type: application/json

{ "username": "api_user", "password": "api_password_123" }
```

### Customer Login (Restaurant)
```http
POST /customer/login
{ "phone": "03001234567", "password": "yourpassword" }
```

### Customer Register (Restaurant)
```http
POST /customer/register
{ "name": "Ali Khan", "phone": "03001234567", "password": "yourpassword" }
```

### Using the Session
All responses return a `session_id`. Pass it as a **Bearer token** on every subsequent request:
```
Authorization: Bearer <session_id>
```

> If a user lacks Odoo permissions for a resource, the API natively returns `403 Forbidden` — enforced by Odoo, not the FastAPI layer.

---

## 🍽️ Restaurant API — Complete Endpoint Reference (`port 8000`)

### Customer Authentication
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/customer/register` | Register a new customer (creates Odoo Portal user) |
| `POST` | `/customer/login` | Login with phone + password |
| `POST` | `/customer/logout` | Invalidate session natively in Odoo |
| `GET` | `/me/profile` | Get current customer profile |
| `PUT` | `/me/profile` | Update name, phone, email, delivery address |
| `PUT` | `/me/location` | Update customer/rider GPS coordinates (lat/lng) |

### Staff Login
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/login` | Admin/staff login with Odoo credentials |

### Product Catalog
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/pos/categories` | List all POS menu categories |
| `GET` | `/pos/products` | List all menu items (with image, description) |
| `GET` | `/pos/products/{id}` | Full product detail page |
| `GET` | `/pos/combos` | List combo products |
| `GET` | `/pos/combos/{id}/choices` | Get combo choice options |
| `GET` | `/products/search?query=` | Search menu items |

### Delivery Orders (Customer-Facing — 24/7)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/order` | **Place a delivery order** (creates Odoo Sale Order + auto-creates Kitchen task) |
| `GET` | `/orders/my` | Customer's full order history |
| `GET` | `/order/{id}` | Order detail + items + delivery status |
| `POST` | `/order/{id}/cancel` | Cancel an order (Odoo blocks if already shipped) |
| `POST` | `/order/{id}/reorder` | Re-place the exact same order in one tap |
| `GET` | `/order/{id}/receipt` | **Print receipt** — structured payload for frontend render |
| `POST` | `/order/{id}/invoice` | Create native Odoo Invoice (account.move) |

### Admin Dashboard
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/admin/dashboard` | Orders today, revenue today, active riders, kitchen queue depth |
| `GET` | `/admin/orders` | All orders with filters (status, date range) |
| `GET` | `/admin/riders` | All registered riders + last known GPS location |
| `POST` | `/admin/riders` | Register a new delivery rider |

### Manager Dashboard
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/manager/orders/pending` | Confirmed orders not yet delivered |
| `GET` | `/manager/revenue` | Revenue breakdown: today / this week / this month |

### Kitchen Dashboard
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/kitchen/queue` | All active orders in kitchen (with items, status, timestamps) |
| `POST` | `/kitchen/order/{id}/ready` | Mark order as ready for pickup — notifies via Odoo chatter |

### Rider Dashboard
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/rider/jobs` | All jobs assigned to the logged-in rider + customer GPS |
| `PUT` | `/me/location` | Broadcast rider GPS location (shared with customer map) |
| `POST` | `/rider/order/{id}/picked_up` | Rider confirms pickup from kitchen |
| `POST` | `/rider/order/{id}/delivered` | Rider confirms delivery — validates Odoo stock.picking |

### Delivery & Tracking
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/delivery/{id}/assign_rider` | Admin assigns rider to an order |
| `GET` | `/delivery/track/{id}` | **Map payload** — customer + rider lat/lng for live map render |

### Real-Time Events (SSE)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/events/orders` | **Server-Sent Events stream** — all dashboards receive pushed updates every 5s |

**Frontend SSE Usage:**
```javascript
const source = new EventSource('http://localhost:8000/events/orders', {
  headers: { 'Authorization': 'Bearer <session_id>' }
});
source.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // data.type === 'order_update' → refresh dashboard
};
```

### Customer Loyalty & Search
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/customer/loyalty?partner_id=` | Loyalty points and available rewards |
| `GET` | `/customers/search?query=` | Search customers by name/email/phone |
| `GET` | `/orders/search` | Search orders by partner or reference |

### Customer Support
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/support/ticket` | Raise a support ticket (creates Odoo project task) |
| `GET` | `/support/my-tickets?phone=` | View customer's own support tickets |

### In-Store POS (Cashier / Kiosk Only)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/pos/categories` | POS category list |
| `POST` | `/pos/order` | Create a POS order (requires an open POS session) |

---

## 🔄 Complete Order Lifecycle Flow

```
1.  Customer  →  POST /customer/register   →   POST /customer/login
2.  Customer  →  GET  /pos/products        →   GET  /pos/products/{id}
3.  Customer  →  POST /order               →   Kitchen task auto-created in Odoo
4.  Admin     →  GET  /admin/orders        →   GET  /admin/dashboard (SSE: /events/orders)
5.  Admin     →  POST /admin/riders        →   POST /delivery/{id}/assign_rider
6.  Manager   →  GET  /manager/orders/pending  →  GET /manager/revenue
7.  Kitchen   →  GET  /kitchen/queue       →   POST /kitchen/order/{id}/ready
8.  Rider     →  GET  /rider/jobs          →   PUT  /me/location  (GPS broadcast every ~10s)
9.  Rider     →  POST /rider/order/{id}/picked_up
10. Customer  →  GET  /delivery/track/{id} (live map: rider + customer coordinates)
11. Rider     →  POST /rider/order/{id}/delivered  →  Odoo stock.picking validated
12. Customer  →  GET  /order/{id}/receipt  →  POST /order/{id}/invoice
```

### Status Lifecycle (Stored natively in Odoo)
```
Kitchen Queue:  Received → Preparing → Ready for Pickup → Picked Up → Delivered
Sale Order:     draft    → sale (confirmed)              → done (delivered) → cancel
Odoo Chatter:   Every status change is logged as a native message_post
```

---

## 💻 Local Development (Docker Compose)

```bash
# Start the full stack
docker compose up -d

# View logs
docker compose logs -f api

# Stop everything
docker compose down
```

### First-Time Odoo Setup
1. Open: [http://localhost:8069/web/database/manager](http://localhost:8069/web/database/manager)
2. Create database: Name `admin`, Email `api_user`, Password `api_password_123`
3. In Odoo UI, install these apps:
   - **Point of Sale** + **Sales** + **Inventory** (Restaurant)
   - **Project** + **Calendar** (Hospital)
   - **eLearning** (School)
   - **CRM** + **Sales** (Real Estate)
   - **Partner Geolocation** (`base_geolocalize`) — required for map tracking

### Seed Dummy Data
```bash
docker compose exec api python seed_data.py
docker compose exec school-api python seed_data.py
docker compose exec hospital-api python seed_hospital.py
docker compose exec realestate-api python seed_estate.py
```

---

## ☁️ Cloud Deployment (Google Cloud Run + Cloud SQL)

### Prerequisites
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com sqladmin.googleapis.com
```

### Step A: Cloud SQL (PostgreSQL 15)
```bash
gcloud sql instances create odoo-postgres \
  --database-version=POSTGRES_15 --tier=db-f1-micro \
  --region=us-central1 --root-password="your-master-password"

gcloud sql databases create admin --instance=odoo-postgres
gcloud sql users create api_user --instance=odoo-postgres --password="api_password_123"

# Save connection name:
gcloud sql instances describe odoo-postgres --format="value(connectionName)"
```

### Step B: Artifact Registry
```bash
gcloud artifacts repositories create chatlium \
  --repository-format docker --location us-central1
```

### Step C: Deploy Odoo
```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/odoo-web:latest . -f Odoo/Dockerfile

gcloud run deploy odoo-web \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/odoo-web:latest \
  --region us-central1 --platform managed --allow-unauthenticated \
  --port 8069 \
  --add-cloudsql-instances YOUR_PROJECT_ID:us-central1:odoo-postgres \
  --set-env-vars HOST=/cloudsql/YOUR_PROJECT_ID:us-central1:odoo-postgres,USER=api_user,PASSWORD=api_password_123
```

### Step D: Deploy API Services
```bash
# Restaurant API
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/restaurent-api:latest Restaurent_api
gcloud run deploy restaurent-api \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/restaurent-api:latest \
  --region us-central1 --platform managed --allow-unauthenticated --port 8000 \
  --set-env-vars ODOO_URL=https://odoo-web-<id>.run.app,ODOO_DB=admin,ODOO_USER=api_user,ODOO_PASSWORD=api_password_123

# Repeat for school-api (8001), hospital-api (8002), realestate-api (8003)
```

> **Note**: Remove `JWT_SECRET` and `SECRET_KEY` from env vars — they are no longer needed.

---

## ⚠️ Troubleshooting

| Error | Fix |
|---|---|
| `Database "admin" does not exist` | Create the database in Odoo UI first |
| `No open POS session found` | Use `POST /order` (delivery) instead of `/pos/order` (in-store only) |
| `Could not update geolocation` | Install **Partner Geolocation** app in Odoo UI |
| `No kitchen task found` | Ensure order was placed via `POST /order` (not `/pos/order`) |
| `Access Denied by Odoo` | The logged-in user lacks Odoo permissions for this operation |
| Cloud Run errors | `gcloud run services logs read odoo-web --region us-central1` |
