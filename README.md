# Chatlium Odoo API Stack

This project runs **Odoo 19.0** as the backend with four independent FastAPI microservices that act as a 100% Odoo-native proxy layer. All authentication, authorization, and business logic is handled natively by Odoo — no custom JWT logic.

| Service | Local URL | Swagger Docs |
|---|---|---|
| 🍽️ Restaurant API | `http://localhost:8000` | `http://localhost:8000/docs` |
| 🏫 School API | `http://localhost:8001` | `http://localhost:8001/docs` |
| 🏥 Hospital API | `http://localhost:8002` | `http://localhost:8002/docs` |
| 🏠 Real Estate API | `http://localhost:8003` | `http://localhost:8003/docs` |
| ⚙️ Odoo UI | `http://localhost:8069` | Odoo web interface |

---

## 🛡️ Authentication (Odoo Native Session)

All 4 APIs use **Odoo's native JSON-RPC session authentication**. There are no custom JWTs. Odoo itself issues and validates every session, enforcing its built-in RBAC and Record Rules automatically.

### Admin / Staff Login (all APIs)
```http
POST /login
{ "username": "api_user", "password": "api_password_123" }
```

### Customer Register (Restaurant only)
```http
POST /customer/register
{ "name": "Ali Khan", "phone": "03001234567", "password": "yourpassword" }
```

### Customer Login (Restaurant only)
```http
POST /customer/login
{ "phone": "03001234567", "password": "yourpassword" }
```

### Using the Session
Every response returns a `session_id`. Pass it as a **Bearer token** on all subsequent requests:
```
Authorization: Bearer <session_id>
```
> If the user lacks Odoo permissions for a resource, the API returns `403 Forbidden` — enforced by Odoo, not FastAPI.

---

## 🍽️ Restaurant API — Full Endpoint Reference (`port 8000`)

### Authentication
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/login` | Admin/staff login with Odoo credentials |
| `POST` | `/customer/register` | Register new customer (creates Odoo Portal user) |
| `POST` | `/customer/login` | Customer login with phone + password |
| `POST` | `/customer/logout` | Invalidate Odoo session natively |

### Customer Profile
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/me` | Returns uid + partner_id of current session |
| `GET` | `/me/profile` | Full profile: name, phone, email, address, GPS location |
| `PUT` | `/me/profile` | Update name, phone, email, street, city |
| `PUT` | `/me/location` | Update GPS coordinates (lat/lng) for tracking |

### Product Catalog
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/pos/categories` | All POS menu categories |
| `GET` | `/pos/products` | All menu items with image, description, price |
| `GET` | `/pos/products/{product_id}` | Full product detail page (image_256, description) |
| `GET` | `/pos/combos` | All combo products |
| `GET` | `/pos/combos/{product_id}/choices` | Combo choice options and extra prices |

### Delivery Orders *(customer-facing, 24/7)*
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/order` | **Place a delivery order** → creates Odoo Sale Order + auto-creates Kitchen task |
| `GET` | `/orders/my` | Customer's full order history with status |
| `GET` | `/order/{order_id}` | Order detail: items, subtotals, delivery status |
| `POST` | `/order/{order_id}/cancel` | Cancel order (Odoo blocks if already shipped) |
| `POST` | `/order/{order_id}/reorder` | Re-place the same order in one tap |

### Receipt & Invoice
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/order/{order_id}/receipt` | Structured receipt payload for frontend print render |
| `POST` | `/order/{order_id}/invoice` | Create native Odoo Invoice (`account.move`) |

### Admin Dashboard
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/admin/dashboard` | Orders today, revenue today, active riders, kitchen queue depth |
| `GET` | `/admin/orders` | All orders — filter by `status`, `date_from`, `date_to` |
| `GET` | `/admin/riders` | All riders with name, phone, last GPS location |
| `POST` | `/admin/riders` | Register a new delivery rider (`name`, `phone`) |

### Manager Dashboard
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/manager/orders/pending` | Confirmed orders not yet delivered + stock.picking state |
| `GET` | `/manager/revenue` | Revenue today / this week / this month |

### Kitchen Dashboard
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/kitchen/queue` | All active kitchen tasks with items + timestamps |
| `POST` | `/kitchen/order/{order_id}/ready` | Mark order ready → logs to Odoo chatter |

### Rider Dashboard
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/rider/jobs` | All jobs assigned to logged-in rider + customer GPS |
| `POST` | `/rider/order/{order_id}/picked_up` | Rider confirms pickup from kitchen |
| `POST` | `/rider/order/{order_id}/delivered` | Rider confirms delivery → validates `stock.picking` |

### Delivery & Map Tracking
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/delivery/{order_id}/assign_rider` | Admin assigns rider (`rider_partner_id`) |
| `GET` | `/delivery/track/{order_id}` | Map payload: customer + rider lat/lng for live map |

### Customer Loyalty & Support
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/customer/loyalty?partner_id=` | Loyalty points, card codes, available rewards |
| `POST` | `/support/ticket` | Raise support ticket (creates Odoo project task) |

### In-Store POS *(cashier/kiosk only)*
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/pos/order` | Create POS order — **requires an open POS session** |

---

## 🔄 Complete A-to-Z Order Lifecycle

```
1.  Customer  →  POST /customer/register → POST /customer/login
2.  Customer  →  GET  /pos/products      → GET  /pos/products/{id}
3.  Customer  →  POST /order             → Kitchen task auto-created in Odoo
                                           Sale Order confirmed in Odoo (state: sale)
4.  Admin     →  GET  /admin/dashboard   → GET  /admin/orders
5.  Admin     →  POST /admin/riders      → POST /delivery/{id}/assign_rider
6.  Manager   →  GET  /manager/orders/pending → GET /manager/revenue
7.  Kitchen   →  GET  /kitchen/queue     → POST /kitchen/order/{id}/ready
                                           (Odoo chatter updated: "Ready for pickup")
8.  Rider     →  GET  /rider/jobs        → PUT  /me/location  (GPS every ~10s)
9.  Rider     →  POST /rider/order/{id}/picked_up
                                           (Odoo chatter updated: "Picked up")
10. Customer  →  GET  /delivery/track/{id}  (live map: rider GPS + customer GPS)
11. Rider     →  POST /rider/order/{id}/delivered
                                           (stock.picking validated, state: done)
12. Customer  →  GET  /order/{id}/receipt → POST /order/{id}/invoice
```

### Order Status Lifecycle (native Odoo)
```
Kitchen Task:  Received → Ready for Pickup → Picked Up → Delivered
Sale Order:    draft    → sale (confirmed)  → done (delivered) | cancel
stock.picking: confirmed → assigned → done
Odoo Chatter:  Every state change is logged via message_post natively
```

> **Dashboard Polling**: Frontend dashboards should poll their endpoint every **5–10 seconds** using `setInterval`. This is the cost-efficient approach for Cloud Run (no persistent connections).

---

## 💻 Local Development

### Start the Stack
```bash
docker compose up -d
```

| Command | Description |
|---|---|
| `docker compose ps` | Check all container statuses |
| `docker compose logs -f api` | Follow Restaurant API logs |
| `docker compose logs -f web` | Follow Odoo logs |
| `docker compose down` | Stop all containers |
| `docker compose up --build` | Rebuild and restart (after code changes) |

### First-Time Odoo Setup
1. Open **[http://localhost:8069/web/database/manager](http://localhost:8069/web/database/manager)**
2. Create a new database:
   - **Database Name**: `admin`
   - **Email / Login**: `api_user`
   - **Password**: `api_password_123`
3. Log into the Odoo UI and install the required apps:

| App to Install | Required By |
|---|---|
| **Point of Sale** | Restaurant (menu/POS) |
| **Sales** | Restaurant (delivery orders) |
| **Inventory** | Restaurant (stock.picking delivery) |
| **Project** | Restaurant (kitchen/delivery tasks) |
| **Partner Geolocation** (`base_geolocalize`) | Restaurant (map tracking) |
| **Project + Calendar** | Hospital API |
| **eLearning** | School API |
| **CRM** | Real Estate API |

### Seed Dummy Data
```bash
docker compose exec api python seed_data.py
docker compose exec school-api python seed_data.py
docker compose exec hospital-api python seed_hospital.py
docker compose exec realestate-api python seed_estate.py
```

### Environment Variables (`.env`)
```env
ODOO_URL=http://web:8069
ODOO_DB=admin
ODOO_USER=api_user
ODOO_PASSWORD=api_password_123

POSTGRES_DB=postgres
POSTGRES_USER=odoo
POSTGRES_PASSWORD=odoo
```
> `JWT_SECRET` and `SECRET_KEY` are legacy variables no longer used by the APIs. They remain in `docker-compose.yml` for backward compat but have no effect.

---

## ☁️ Cloud Deployment (Google Cloud Run + Cloud SQL)

Cloud Run runs each service as a separate stateless container. Odoo requires sub-millisecond database latency, so **Cloud SQL (PostgreSQL 15)** is used instead of a separate container.

### Prerequisites
```bash
# Install gcloud CLI: https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com
```

---

### Step 1 — Create Cloud SQL (PostgreSQL 15)
```bash
# Create the database instance
gcloud sql instances create odoo-postgres \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --root-password="YOUR_ROOT_PASSWORD"

# Create the Odoo database
gcloud sql databases create admin --instance=odoo-postgres

# Create the API user
gcloud sql users create api_user \
  --instance=odoo-postgres \
  --password="api_password_123"

# Save the connection name — you'll need it in every deploy command
gcloud sql instances describe odoo-postgres --format="value(connectionName)"
# Output example: my-project:us-central1:odoo-postgres
```

---

### Step 2 — Create Artifact Registry
```bash
gcloud artifacts repositories create chatlium \
  --repository-format=docker \
  --location=us-central1 \
  --description="Chatlium container images"

# Authenticate Docker to push images
gcloud auth configure-docker us-central1-docker.pkg.dev
```

---

### Step 3 — Build & Deploy Odoo
```bash
# Build Odoo image (run from repo root)
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/odoo-web:latest \
  -f Odoo/Dockerfile .

# Deploy Odoo to Cloud Run
gcloud run deploy odoo-web \
  --image=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/odoo-web:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --port=8069 \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --add-cloudsql-instances=YOUR_PROJECT_ID:us-central1:odoo-postgres \
  --set-env-vars=HOST=/cloudsql/YOUR_PROJECT_ID:us-central1:odoo-postgres,USER=api_user,PASSWORD=api_password_123,DB=admin
```
After deploy, copy the Cloud Run URL (e.g. `https://odoo-web-xxxx.run.app`).
Open it in your browser, create the database, and **install all required Odoo apps** listed in the Local Setup section.

---

### Step 4 — Deploy Restaurant API
```bash
# Build
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/restaurent-api:latest \
  Restaurent_api/

# Deploy
gcloud run deploy restaurent-api \
  --image=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/restaurent-api:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --port=8000 \
  --memory=512Mi \
  --cpu=1 \
  --set-env-vars=ODOO_URL=https://odoo-web-xxxx.run.app,ODOO_DB=admin,ODOO_USER=api_user,ODOO_PASSWORD=api_password_123
```

---

### Step 5 — Deploy School API
```bash
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/school-api:latest \
  School_api/

gcloud run deploy school-api \
  --image=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/school-api:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --port=8001 \
  --memory=512Mi \
  --cpu=1 \
  --set-env-vars=ODOO_URL=https://odoo-web-xxxx.run.app,ODOO_DB=admin,ODOO_USER=api_user,ODOO_PASSWORD=api_password_123
```

---

### Step 6 — Deploy Hospital API
```bash
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/hospital-api:latest \
  Hospital_api/

gcloud run deploy hospital-api \
  --image=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/hospital-api:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --port=8002 \
  --memory=512Mi \
  --cpu=1 \
  --set-env-vars=ODOO_URL=https://odoo-web-xxxx.run.app,ODOO_DB=admin,ODOO_USER=api_user,ODOO_PASSWORD=api_password_123
```

---

### Step 7 — Deploy Real Estate API
```bash
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/realestate-api:latest \
  RealEstate_api/

gcloud run deploy realestate-api \
  --image=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/realestate-api:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --port=8003 \
  --memory=512Mi \
  --cpu=1 \
  --set-env-vars=ODOO_URL=https://odoo-web-xxxx.run.app,ODOO_DB=admin,ODOO_USER=api_user,ODOO_PASSWORD=api_password_123
```

---

### Cloud Run — Useful Commands
```bash
# List all deployed services
gcloud run services list --region=us-central1

# View live logs for any service
gcloud run services logs read restaurent-api --region=us-central1
gcloud run services logs read odoo-web --region=us-central1

# Update env vars without redeploy
gcloud run services update restaurent-api \
  --region=us-central1 \
  --set-env-vars=ODOO_URL=https://new-odoo-url.run.app

# Delete a service
gcloud run services delete restaurent-api --region=us-central1
```

---

## ⚠️ Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `Database "admin" does not exist` | Odoo DB not initialized | Create it via Odoo UI at `/web/database/manager` |
| `Invalid Odoo credentials` | Wrong login/password | Check `ODOO_USER` + `ODOO_PASSWORD` env vars |
| `No open POS session found` | Wrong endpoint | Use `POST /order` (delivery). `/pos/order` is in-store only |
| `Could not update geolocation` | Missing Odoo app | Install **Partner Geolocation** (`base_geolocalize`) in Odoo |
| `No kitchen task found` | Order not placed via API | Ensure order placed via `POST /order`, not `/pos/order` |
| `Invalid field 'groups_id'` | Odoo version mismatch | Already fixed — register uses two-step create + write |
| `Access Denied by Odoo (403)` | Odoo RBAC | The logged-in user lacks permissions; check Odoo Access Rights |
| `Odoo did not return a session_id` | Auth failed silently | Verify `ODOO_DB` matches the database name exactly |
| Cloud Run `500` errors | Container startup issue | `gcloud run services logs read SERVICE_NAME --region=us-central1` |
| Cloud SQL connection refused | Missing IAM / socket | Ensure `--add-cloudsql-instances` flag is set in the Odoo deploy |
