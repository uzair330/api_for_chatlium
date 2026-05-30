FROM odoo:19.0

USER root

# Create necessary directories
RUN mkdir -p /etc/odoo /mnt/extra-addons

# Copy custom configurations and scripts
COPY Odoo/entrypoint-custom.sh /entrypoint-custom.sh
COPY Odoo/odoo.conf /etc/odoo/odoo.conf

# Make the entrypoint executable
RUN chmod +x /entrypoint-custom.sh

# Copy any custom addons from the repository (if they exist)
# Using a wildcard ensures the build doesn't fail if the directory is empty
COPY addons* /mnt/extra-addons/

# Ensure Odoo user owns the directories
RUN chown -R odoo:odoo /var/lib/odoo /etc/odoo /mnt/extra-addons /entrypoint-custom.sh

USER odoo

# Use the custom entrypoint
ENTRYPOINT ["/entrypoint-custom.sh"]

CMD ["odoo"]
