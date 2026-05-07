import os
import xmlrpc.client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

def seed_test_data():
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        print("Connected to Odoo...")

        # 1. Create POS Categories
        fast_food_cat = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'pos.category', 'create', [{'name': 'Fast Food'}])
        drinks_cat = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'pos.category', 'create', [{'name': 'Drinks'}])
        desserts_cat = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'pos.category', 'create', [{'name': 'Desserts'}])
        print(f"Created Categories: Fast Food, Drinks, Desserts")

        # 2. Create Base Products
        products_data = [
            {'name': 'Classic Burger', 'price': 12.0, 'cat': fast_food_cat},
            {'name': 'Cheese Pizza', 'price': 15.0, 'cat': fast_food_cat},
            {'name': 'French Fries', 'price': 4.5, 'cat': fast_food_cat},
            {'name': 'Coca Cola', 'price': 2.5, 'cat': drinks_cat},
            {'name': 'Orange Juice', 'price': 3.5, 'cat': drinks_cat},
            {'name': 'Chocolate Cake', 'price': 6.0, 'cat': desserts_cat},
        ]

        product_ids = {}
        for p in products_data:
            p_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.product', 'create', [{
                'name': p['name'],
                'list_price': p['price'],
                'available_in_pos': True,
                'pos_categ_ids': [(4, p['cat'])],
            }])
            product_ids[p['name']] = p_id
            print(f"Created Product: {p['name']} (ID: {p_id})")

        # 3. Create Odoo 18 Combo Choices
        # Choice 1: The Main Drink
        drink_combo_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.combo', 'create', [{
            'name': 'Select Your Drink',
        }])
        # Add products to the choice
        for drink in ['Coca Cola', 'Orange Juice']:
            models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.combo.item', 'create', [{
                'combo_id': drink_combo_id,
                'product_id': product_ids[drink],
                'extra_price': 0.0
            }])

        # 4. Create the Combo Product (The "Burger Deal")
        combo_product_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.product', 'create', [{
            'name': 'Burger & Drink Deal',
            'list_price': 14.0,
            'available_in_pos': True,
            'type': 'combo',
            'pos_categ_ids': [(4, fast_food_cat)],
            'combo_ids': [(4, drink_combo_id)]
        }])
        print(f"Created Combo Product: Burger & Drink Deal (ID: {combo_product_id})")

        # 5. Create Test Customer
        partner_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
            'name': 'Test User',
            'phone': '+123456789',
        }])
        print(f"Created Test Customer: Test User (ID: {partner_id}, Phone: +123456789)")

        print("\nSeed successful! Advanced Odoo 18 features (Combos) are now available.")

    except Exception as e:
        print(f"Error seeding data: {e}")

if __name__ == "__main__":
    seed_test_data()
