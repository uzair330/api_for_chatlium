# Google Cloud Run Deployment (Option 3: Cloud SQL + Cloud Run)

This guide walks you through deploying Odoo and the four FastAPI services manually to Google Cloud Run, using a managed Cloud SQL PostgreSQL 15 database for sub-millisecond database connection latency.

## Prerequisites

- Install and authenticate `gcloud`: [https://cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)
- Enable required APIs:
  ```bash
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com sqladmin.googleapis.com
  ```

## 1. Setup Cloud SQL (PostgreSQL 15)

Odoo requires extremely low latency to its database. Using Cloud SQL in the same region as Cloud Run achieves this via local Unix sockets.

1. **Create PostgreSQL Instance**:
   ```bash
   gcloud sql instances create odoo-postgres \
     --database-version=POSTGRES_15 \
     --tier=db-f1-micro \
     --region=us-central1 \
     --root-password="your-master-password"
   ```
2. **Create Database**:
   ```bash
   gcloud sql databases create admin --instance=odoo-postgres
   ```
3. **Create User**:
   ```bash
   gcloud sql users create api_user --instance=odoo-postgres --password="api_password_123"
   ```
4. **Get Connection Name**:
   ```bash
   gcloud sql instances describe odoo-postgres --format="value(connectionName)"
   # Save this. It looks like: my-project:us-central1:odoo-postgres
   ```

## 2. Setup Artifact Registry

Create a repository to store the Docker images:
```bash
gcloud artifacts repositories create chatlium \
  --repository-format docker \
  --location us-central1
```

## 3. Deploy Odoo to Cloud Run

The Odoo custom image (`Odoo/Dockerfile`) contains a custom wrapper to resolve Cloud Run's port injection while ensuring database connectivity.

1. **Build Odoo**:
   ```bash
   gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/odoo-web:latest . -f Odoo/Dockerfile
   ```

2. **Deploy Odoo**:
   ```bash
   gcloud run deploy odoo-web \
     --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/odoo-web:latest \
     --region us-central1 \
     --platform managed \
     --allow-unauthenticated \
     --port 8069 \
     --add-cloudsql-instances YOUR_PROJECT_ID:us-central1:odoo-postgres \
     --set-env-vars HOST=/cloudsql/YOUR_PROJECT_ID:us-central1:odoo-postgres,USER=api_user,PASSWORD=api_password_123
   ```
   *Wait for the URL output. Open the URL in your browser to verify Odoo starts and install required modules (CRM, POS, etc.).*

## 4. Deploy API Services

Each API service is deployed in the same way. You must provide the `ODOO_URL` you got from the previous step.

**Restaurant API**:
1. Build:
   ```bash
   gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/restaurent-api:latest Restaurent_api
   ```
2. Deploy:
   ```bash
   gcloud run deploy restaurent-api \
     --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/chatlium/restaurent-api:latest \
     --region us-central1 \
     --platform managed \
     --allow-unauthenticated \
     --port 8000 \
     --set-env-vars ODOO_URL=https://odoo-web-<id>.run.app,ODOO_DB=admin,ODOO_USER=api_user,ODOO_PASSWORD=api_password_123,JWT_SECRET=supersecret123,SECRET_KEY=supersecret123
   ```

*(Repeat step 4 for `School_api`, `Hospital_api`, and `RealEstate_api` changing the folder and service names accordingly).*
