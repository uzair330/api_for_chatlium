# Chatlium Odoo API Stack

This project runs Odoo 19.0 with four FastAPI bridge services:

| Service | Local URL | Docs |
| --- | --- | --- |
| Restaurant API | `http://localhost:8000` | `http://localhost:8000/docs` |
| School API | `http://localhost:8001` | `http://localhost:8001/docs` |
| Hospital API | `http://localhost:8002` | `http://localhost:8002/docs` |
| Real Estate API | `http://localhost:8003` | `http://localhost:8003/docs` |
| Odoo UI | `http://localhost:8069` | Odoo web interface |

## Local Docker Compose

Use Docker Compose for local development. This starts PostgreSQL, Odoo, and all four API services.

### Start

```bash
docker compose up -d
```

Check status:

```bash
docker compose ps
```

Follow API logs:

```bash
docker compose logs -f api school-api hospital-api realestate-api
```

Stop everything:

```bash
docker compose down
```

### First-Time Odoo Setup

Before API login and seed scripts work, the Odoo database must exist.

Open:

```text
http://localhost:8069
```

Odoo database manager:

```text
http://localhost:8069/web/database/manager
```

Create a database using the same values from `.env`:

```text
Database name: admin
Email/Login: api_user
Password: api_password_123
```

If Odoo asks for a master password, try:

```text
admin
```

The master password is for Odoo database management operations such as creating, duplicating, backing up, restoring, or deleting databases. It is separate from the Odoo user login password.

Install the Odoo apps needed by the APIs:

```text
Point of Sale
CRM
Project
Calendar
eLearning
Sales
```

Local `.env` defaults:

```env
ODOO_URL=http://web:8069
ODOO_DB=admin
ODOO_USER=api_user
ODOO_PASSWORD=api_password_123
JWT_SECRET=supersecret123
SECRET_KEY=supersecret123
```

Official Odoo references:

- Odoo 19 database management: https://www.odoo.com/documentation/19.0/administration.html
- Odoo 19 on-premise database manager path: https://www.odoo.com/documentation/19.0/administration/on_premise.html
- Official Odoo Docker image: https://hub.docker.com/_/odoo/

## Auth And Login

There is no general public signup endpoint in these APIs.

Users and records are created in Odoo or by the seed scripts. The APIs authenticate those Odoo users or seeded records and return JWT tokens.

### Staff Login

All four APIs support staff login:

```text
POST /token
```

Body:

```json
{
  "username": "api_user",
  "password": "api_password_123"
}
```

In Swagger:

1. Open one of the `/docs` URLs.
2. Open `POST /token`.
3. Click `Try it out`.
4. Enter the JSON above.
5. Copy the returned `access_token`.
6. Click `Authorize`.
7. Enter `Bearer <access_token>`.

### Restaurant Customer Login

After running the restaurant seed script:

```text
POST http://localhost:8000/customer/login
```

Body:

```json
{
  "phone": "+123456789"
}
```

### School Student Login

After running the school seed script:

```text
POST http://localhost:8001/student/login
```

Body:

```json
{
  "student_ref": "STU001"
}
```

Other seeded student refs:

```text
STU002
STU003
```

## Seed Dummy Data

Run these commands after Odoo database creation and required app installation.

Restaurant:

```bash
docker compose exec api python seed_data.py
```

School:

```bash
docker compose exec school-api python seed_data.py
```

Large school dataset:

```bash
docker compose exec school-api python seed_data_large.py
```

Hospital:

```bash
docker compose exec hospital-api python seed_hospital.py
```

Real Estate:

```bash
docker compose exec realestate-api python seed_estate.py
```

## Quick Curl Tests

Restaurant staff login:

```bash
curl -X POST http://localhost:8000/token \
  -H "Content-Type: application/json" \
  -d '{"username":"api_user","password":"api_password_123"}'
```

School staff login:

```bash
curl -X POST http://localhost:8001/token \
  -H "Content-Type: application/json" \
  -d '{"username":"api_user","password":"api_password_123"}'
```

Hospital staff login:

```bash
curl -X POST http://localhost:8002/token \
  -H "Content-Type: application/json" \
  -d '{"username":"api_user","password":"api_password_123"}'
```

Real Estate staff login:

```bash
curl -X POST http://localhost:8003/token \
  -H "Content-Type: application/json" \
  -d '{"username":"api_user","password":"api_password_123"}'
```

## Google Cloud Run

Cloud Run does not run `docker-compose.yml`. Deploy each container separately:

- `odoo-web`
- `restaurent-api`
- `school-api`
- `hospital-api`
- `realestate-api`

The Odoo Cloud Run image is defined at:

```text
Odoo/Dockerfile
```

It uses `odoo:19.0` and copies repo custom addons into:

```text
/mnt/extra-addons
```

The Odoo image is built with:

```text
cloudbuild-odoo.yaml
```

### Cloud Run Requirements

Install and authenticate the Google Cloud CLI first.

Enable required APIs:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com sqladmin.googleapis.com
```

Cloud Run does not include the local PostgreSQL container. Use Cloud SQL for PostgreSQL or another managed PostgreSQL database.

For Cloud SQL, set:

```bash
export CLOUD_SQL_INSTANCE="<project>:<region>:<instance>"
export ODOO_DB_USER="<postgres-user>"
export ODOO_DB_PASSWORD="<postgres-password>"
```

When `CLOUD_SQL_INSTANCE` is set, the deploy script:

- Deploys Odoo with `--add-cloudsql-instances`.
- Sets Odoo `HOST` to `/cloudsql/<INSTANCE_CONNECTION_NAME>`.
- Lets Odoo connect over the Cloud SQL Unix socket.

For a non-Cloud SQL PostgreSQL provider, set:

```bash
export ODOO_DB_HOST="<postgres-host>"
export ODOO_DB_USER="<postgres-user>"
export ODOO_DB_PASSWORD="<postgres-password>"
```

### Cloud Run Environment

Set the Odoo/API credentials:

```bash
export ODOO_DB="admin"
export ODOO_USER="api_user"
export ODOO_PASSWORD="api_password_123"
export JWT_SECRET="<secure-jwt-secret>"
export SECRET_KEY="<secure-jwt-secret>"
```

Optional Artifact Registry repository name:

```bash
export AR_REPOSITORY="chatlium"
```

Images are pushed to:

```text
<region>-docker.pkg.dev/<project>/<repository>/<service>:latest
```

### Deploy To Cloud Run

```bash
chmod +x deploy-to-cloud-run.sh
./deploy-to-cloud-run.sh <GCP_PROJECT> [REGION]
```

Example:

```bash
export CLOUD_SQL_INSTANCE="my-project:us-central1:odoo-postgres"
export ODOO_DB_USER="odoo"
export ODOO_DB_PASSWORD="<postgres-password>"
export ODOO_DB="admin"
export ODOO_USER="api_user"
export ODOO_PASSWORD="api_password_123"
export JWT_SECRET="<secure-jwt-secret>"
export SECRET_KEY="<secure-jwt-secret>"
./deploy-to-cloud-run.sh my-project us-central1
```

After deploy, open the `odoo-web` Cloud Run URL, create the Odoo database, install required apps, then run seed scripts from local containers or one-off Cloud Run jobs if needed.

For Cloud Run, the Odoo database manager URL is:

```text
https://<odoo-web-cloud-run-url>/web/database/manager
```

Use that page to create, duplicate, backup, restore, or delete Odoo databases. The database name should match `ODOO_DB`, for example `admin`.

Cloud Run container storage is ephemeral. For production Odoo file storage and attachments, use a persistent storage strategy instead of relying on files written inside the container.

Official Google Cloud references:

- Cloud Run container runtime contract: https://docs.cloud.google.com/run/docs/container-contract
- Cloud Run environment variables: https://cloud.google.com/run/docs/configuring/services/environment-variables
- Connect Cloud Run to Cloud SQL for PostgreSQL: https://cloud.google.com/sql/docs/postgres/connect-run
- Artifact Registry Docker repositories: https://cloud.google.com/artifact-registry/docs/docker/store-docker-container-images

## Troubleshooting

If API login or seed scripts fail with:

```text
database "admin" does not exist
```

Create the Odoo database in the Odoo UI first.

If a seed script fails with a missing Odoo model, install the matching Odoo app:

- Restaurant needs Point of Sale.
- School LMS needs eLearning.
- Hospital needs Project and Calendar.
- Real Estate needs CRM and Sales.

Local checks:

```bash
docker compose ps
docker compose logs web
docker compose logs api school-api hospital-api realestate-api
```

Cloud Run checks:

```bash
gcloud run services list
gcloud run services describe odoo-web --region <REGION>
gcloud run services logs read odoo-web --region <REGION>
```
