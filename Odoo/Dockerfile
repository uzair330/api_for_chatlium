FROM odoo:19.0

# Cloud Run deploys one container per service, so Odoo needs its own image.
# The build context is the repository root; this copies the same custom addons
# directory that docker-compose mounts locally.
COPY addons /mnt/extra-addons

EXPOSE 8069
