import os
import xmlrpc.client
import random
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

def seed_estate():
    print("Connecting to Odoo for Real Estate Seeding...")
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

    # 1. Create Category
    categ_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'search', [[['name', '=', 'Real Estate']]])
    if not categ_ids:
        categ_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'create', [{'name': 'Real Estate'}])
    else:
        categ_id = categ_ids[0]

    # 2. Create Properties
    properties = [
        ("Modern Luxury Villa", 50000000, "House", "DHA Phase 6, Lahore"),
        ("Smart City Apartment", 12000000, "Flat", "Gulberg, Islamabad"),
        ("Riverside Plot", 8000000, "Plot", "Bahria Town, Karachi"),
        ("Commercial Plaza Space", 25000000, "Shop", "Blue Area, Islamabad"),
        ("Family Home", 18000000, "House", "Model Town, Lahore")
    ]
    
    prop_ids = []
    for name, price, p_type, loc in properties:
        p_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.template', 'create', [{
            'name': name,
            'list_price': price,
            'categ_id': categ_id,
            'description_sale': f"Type: {p_type} | Location: {loc} | 3 Bedrooms | 2 Bathrooms",
            'type': 'service',
            'sale_ok': True
        }])
        prop_ids.append(p_id)
    print(f"Created {len(prop_ids)} Properties.")

    # 3. Create Agents
    agent_tag = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'search', [[['name', '=', 'Agent']]])
    if not agent_tag:
        agent_tag = [models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'create', [{'name': 'Agent'}])]
    
    agents = ["Zeeshan Realtor", "Ayesha Properties", "Irfan Real Estate"]
    for name in agents:
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
            'name': name,
            'category_id': [(4, agent_tag[0])],
            'phone': f"+92-300-{random.randint(1000000, 9999999)}"
        }])
    print("Created 3 Agents.")

    # 4. Create Inquiries (CRM Leads)
    inquirers = ["Hamza Malik", "Sara Khan", "Ali Raza"]
    for i in range(len(inquirers)):
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'crm.lead', 'create', [{
            'name': f"Inquiry for {properties[i][0]}",
            'contact_name': inquirers[i],
            'phone': f"+92-321-{random.randint(1000000, 9999999)}",
            'description': f"I am interested in buying the {properties[i][0]} at {properties[i][3]}.",
            'type': 'lead'
        }])
    print("Created 3 Inquiries.")

if __name__ == "__main__":
    seed_estate()
