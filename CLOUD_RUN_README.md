Quick Cloud Run deployment notes

Prerequisites
- Install and authenticate gcloud: https://cloud.google.com/sdk/docs/install
- Enable required APIs: Cloud Run, Cloud Build, Artifact Registry, and Cloud SQL Admin
  - gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com sqladmin.googleapis.com
- Set `PROJECT` and optionally `REGION` (default `us-central1`)

Environment variables
- Cloud Run does not run `docker-compose.yml`. Each service is deployed as its own container.
- Odoo has its own image at `Odoo/Dockerfile`. It is built with `cloudbuild-odoo.yaml` so the repo-level `addons/` directory is copied into `/mnt/extra-addons`.
- These services require Odoo and JWT secrets. Set them after deploy with:
  - `gcloud run services update <service> --update-env-vars KEY=VALUE` or
  - `gcloud run deploy <service> --set-env-vars KEY=VALUE` during deploy

Odoo database
- The local compose stack includes Postgres, but Cloud Run does not. Use Cloud SQL for PostgreSQL or another managed PostgreSQL database.
- Before running the deploy script, export database env vars that point to your managed PostgreSQL instance:
  - `ODOO_DB_USER`
  - `ODOO_DB_PASSWORD`
- If using Cloud SQL, also export:
  - `CLOUD_SQL_INSTANCE`, for example `my-project:us-central1:odoo-postgres`
- When `CLOUD_SQL_INSTANCE` is set, the script deploys Odoo with `--add-cloudsql-instances` and uses the Cloud SQL Unix socket host `/cloudsql/<INSTANCE_CONNECTION_NAME>`.
- If you are not using Cloud SQL, set `ODOO_DB_HOST` to your PostgreSQL hostname.
- The API services need:
  - `ODOO_URL` set to the deployed `odoo-web` URL
  - `ODOO_DB`
  - `ODOO_USER`
  - `ODOO_PASSWORD`
  - `JWT_SECRET` / `SECRET_KEY`

Deploy (automated)
- From repo root run:

```bash
chmod +x deploy-to-cloud-run.sh
export CLOUD_SQL_INSTANCE="<project>:<region>:<instance>"
export ODOO_DB_USER="<postgres-user>"
export ODOO_DB_PASSWORD="<postgres-password>"
export ODOO_DB="admin"
export ODOO_USER="api_user"
export ODOO_PASSWORD="api_password_123"
export JWT_SECRET="<secure-jwt-secret>"
export SECRET_KEY="<secure-jwt-secret>"
./deploy-to-cloud-run.sh <GCP_PROJECT> [REGION]
```

Notes & recommendations
- The API containers run Uvicorn on port 8000. The Odoo container runs on port 8069.
- Images are pushed to Artifact Registry at `<region>-docker.pkg.dev/<project>/chatlium/...`. Override the repository name with `AR_REPOSITORY`.
- For production, supply secure values for `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_PASSWORD`, and `JWT_SECRET`.
- Cloud Run container storage is ephemeral. For production Odoo file storage and attachments, configure a persistent storage strategy such as Cloud Storage-backed handling or another Odoo-compatible filestore approach.
- Restrict service access for private APIs by removing `--allow-unauthenticated`.
