import os
import xmlrpc.client

# Internal Docker address is 'web', host address is 'localhost'
ODOO_URL = os.getenv("ODOO_URL", "http://web:8069")
ODOO_DB = os.getenv("ODOO_DB", "admin")
ODOO_ADMIN_USER = os.getenv("ODOO_USER")
ODOO_ADMIN_PASSWORD = os.getenv("ODOO_PASSWORD")

def create_api_user():
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")

        # 1. Check connection
        version = common.version()
        print(f"Connected to Odoo version: {version.get('server_version')}")

        # 2. Authenticate as admin
        uid = common.authenticate(ODOO_DB, ODOO_ADMIN_USER, ODOO_ADMIN_PASSWORD, {})
        if not uid:
            print("Authentication failed! Check admin password.")
            return

        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

        # 3. Create the API User
        new_user_id = models.execute_kw(ODOO_DB, uid, ODOO_ADMIN_PASSWORD, 'res.users', 'create', [{
            'name': 'WhatsApp API User',
            'login': 'api_user',
            'password': 'api_password_123',
        }])

        print(f"\nSuccess! API User created with ID: {new_user_id}")
        print("  Login:    api_user")
        print("  Password: api_password_123")

    except ConnectionRefusedError:
        print("Could not connect to Odoo. Is the 'web' container running?")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    create_api_user()
