import os
import xmlrpc.client
import jwt
import datetime
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Security Settings
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Odoo Configuration
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
# System defaults (for internal admin tasks)
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

app = FastAPI(title="Odoo Restaurant POS API")
security = HTTPBearer()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Models ---
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class LoginRequest(BaseModel):
    username: str
    password: str

class CustomerLoginRequest(BaseModel):
    phone: str

class POSOrderItem(BaseModel):
    product_id: int
    quantity: float
    combo_choices: Optional[List[int]] = None  # List of selected product IDs within the combo
    note: Optional[str] = None

class POSOrderRequest(BaseModel):
    partner_id: int
    items: List[POSOrderItem]

class SupportTicket(BaseModel):
    customer_name: str
    phone: str
    issue_type: str  # e.g., Billing, Food Quality, Technical
    message: str
    priority: str = "0"  # 0: Low, 1: High
    order_id: Optional[int] = None

# --- Auth Helpers ---
def create_tokens(subject: str, payload: dict = {}):
    access_delta = datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_delta = datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    data = {"sub": subject, **payload}
    access_token = jwt.encode({**data, "exp": datetime.datetime.utcnow() + access_delta}, SECRET_KEY, algorithm=ALGORITHM)
    refresh_token = jwt.encode({**data, "refresh": True, "exp": datetime.datetime.utcnow() + refresh_delta}, SECRET_KEY, algorithm=ALGORITHM)
    
    return access_token, refresh_token

def verify_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def get_current_user(auth: HTTPAuthorizationCredentials = Security(security)):
    return verify_token(auth.credentials)

# --- Odoo Helper ---
def get_odoo_models(user=None, password=None):
    """Connects to Odoo. Uses provided credentials or system defaults."""
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        login = user or ODOO_USER
        pwd = password or ODOO_PASSWORD
        uid = common.authenticate(ODOO_DB, login, pwd, {})
        if not uid:
            return None, None
        return uid, xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    except Exception as e:
        logger.error(f"Odoo Connection Error: {e}")
        return None, None

# --- Endpoints ---

@app.post("/token", response_model=Token, tags=["Authentication"])
def login(req: LoginRequest):
    """Authenticates against Odoo's real users (res.users)"""
    uid, models = get_odoo_models(req.username, req.password)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid Odoo credentials")
    
    # Get user details from Odoo
    user_data = models.execute_kw(ODOO_DB, uid, req.password, 'res.users', 'read', [uid], {'fields': ['name', 'login']})
    
    access, refresh = create_tokens(str(uid), {"name": user_data[0]['name'], "login": user_data[0]['login'], "type": "staff"})
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@app.get("/me", tags=["Authentication"])
def get_me(user=Depends(get_current_user)):
    """Verifies the token and returns the logged in user info"""
    return {
        "uid": user.get("sub"),
        "name": user.get("name"),
        "login": user.get("login"),
        "type": user.get("type", "customer")
    }

@app.post("/refresh", response_model=Token, tags=["Authentication"])
def refresh_token(auth: HTTPAuthorizationCredentials = Security(security)):
    """Exchanges a valid Refresh Token for a new set of tokens"""
    user = verify_token(auth.credentials)
    
    if not user.get("refresh"):
        raise HTTPException(status_code=401, detail="This is not a refresh token")
    
    # Generate new tokens
    access, refresh = create_tokens(user["sub"], {
        "name": user.get("name"),
        "login": user.get("login"),
        "type": user.get("type")
    })
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@app.post("/customer/login", response_model=Token, tags=["Authentication"])
def customer_login(req: CustomerLoginRequest):
    """Customer login via phone number lookup"""
    uid, models = get_odoo_models()
    partner = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_read',
        [[['phone', '=', req.phone]]], {'limit': 1, 'fields': ['id', 'name']})
    
    if not partner:
        raise HTTPException(status_code=404, detail="Customer phone not found")
    
    access, refresh = create_tokens(str(partner[0]['id']), {"name": partner[0]['name'], "type": "customer"})
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@app.get("/pos/categories", tags=["POS Operations"])
def get_categories(user=Depends(get_current_user)):
    uid, models = get_odoo_models()
    return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'pos.category', 'search_read', [], {'fields': ['id', 'name']})

@app.get("/pos/products", tags=["Product Catalog"])
def get_products(category_id: Optional[int] = None, user=Depends(get_current_user)):
    uid, models = get_odoo_models()
    domain = [[['available_in_pos', '=', True]]]
    if category_id:
        domain[0].append(['pos_categ_ids', 'in', [category_id]])
    
    return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.product', 'search_read',
        domain, {'fields': ['id', 'display_name', 'list_price']})

@app.post("/pos/order", tags=["POS Operations"])
def create_order(order: POSOrderRequest, user=Depends(get_current_user)):
    uid, models = get_odoo_models()
    sessions = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'pos.session', 'search_read',
        [[['state', '=', 'opened']]], {'limit': 1, 'fields': ['id']})
    if not sessions:
        raise HTTPException(status_code=400, detail="No open POS session found.")

    order_payload = {
        'session_id': sessions[0]['id'],
        'partner_id': order.partner_id,
        'lines': [],
    }

    for item in order.items:
        line = {
            'product_id': item.product_id,
            'qty': item.quantity,
        }
        if item.note:
            line['note'] = item.note
        # Handle combo choices if applicable (Odoo 18 structure)
        if item.combo_choices:
            line['combo_line_ids'] = [(4, choice_id) for choice_id in item.combo_choices]
        
        order_payload['lines'].append((0, 0, line))

    order_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'pos.order', 'create', [order_payload])
    return {"status": "success", "order_id": order_id}

@app.get("/pos/combos", tags=["Product Catalog"])
def get_combos(user=Depends(get_current_user)):
    """Fetch products that are part of a combo (Odoo 18)"""
    uid, models = get_odoo_models()
    return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.product', 'search_read',
        [[['available_in_pos', '=', True], ['type', '=', 'combo']]], 
        {'fields': ['id', 'display_name', 'list_price']})

@app.get("/pos/combos/{product_id}/choices", tags=["Product Catalog"])
def get_combo_choices(product_id: int, user=Depends(get_current_user)):
    """Fetch the available options for a specific combo product"""
    uid, models = get_odoo_models()
    product = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.product', 'read', 
        [product_id], {'fields': ['combo_ids']})
    
    if not product or not product[0].get('combo_ids'):
        raise HTTPException(status_code=404, detail="No combo choices found for this product")

    combos = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'pos.combo', 'read',
        [product[0]['combo_ids']], {'fields': ['id', 'name', 'combo_line_ids']})
    
    result = []
    for combo in combos:
        lines = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'pos.combo.line', 'read',
            [combo['combo_line_ids']], {'fields': ['product_id', 'extra_price']})
        
        result.append({
            "combo_id": combo['id'],
            "name": combo['name'],
            "choices": [{"id": l['product_id'][0], "name": l['product_id'][1], "extra_price": l['extra_price']} for l in lines]
        })
    
    return result

@app.get("/customer/loyalty", tags=["Customer & Loyalty"])
def get_loyalty_points(user=Depends(get_current_user)):
    """Fetch loyalty points for the logged-in customer"""
    uid, models = get_odoo_models()
    partner_id = int(user.get("sub"))
    
    cards = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'loyalty.card', 'search_read',
        [[['partner_id', '=', partner_id]]], {'fields': ['points', 'program_id', 'code']})
    
    if not cards:
        return {"points": 0, "rewards": [], "message": "No loyalty card found"}

    program_ids = [c['program_id'][0] for c in cards]
    rewards = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'loyalty.reward', 'search_read',
        [[['program_id', 'in', program_ids]]], {'fields': ['id', 'description', 'required_points']})

    return {
        "points": sum(c['points'] for c in cards),
        "card_codes": [c['code'] for c in cards],
        "available_rewards": rewards
    }

@app.get("/customers/search", tags=["Search"])
def search_customers(query: str, user=Depends(get_current_user)):
    """Search for customers by name, email, or phone"""
    uid, models = get_odoo_models()
    domain = ['|', '|', 
              ['name', 'ilike', query], 
              ['email', 'ilike', query], 
              ['phone', 'ilike', query]]
    return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_read',
        [domain], {'fields': ['id', 'name', 'email', 'phone'], 'limit': 20})

@app.get("/products/search", tags=["Search"])
def search_products(query: str, user=Depends(get_current_user)):
    """Search for POS-enabled products by name or internal reference"""
    uid, models = get_odoo_models()
    domain = [['available_in_pos', '=', True], 
              '|', 
              ['name', 'ilike', query], 
              ['default_code', 'ilike', query]]
    return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.product', 'search_read',
        [domain], {'fields': ['id', 'display_name', 'list_price'], 'limit': 20})

@app.get("/orders/search", tags=["Search"])
def search_orders(partner_id: Optional[int] = None, reference: Optional[str] = None, user=Depends(get_current_user)):
    """Search for POS orders by partner or reference"""
    uid, models = get_odoo_models()
    domain = []
    if partner_id:
        domain.append(['partner_id', '=', partner_id])
    if reference:
        domain.append(['name', 'ilike', reference])
    
    return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'pos.order', 'search_read',
        [domain], {'fields': ['id', 'name', 'date_order', 'amount_total', 'state'], 'limit': 20})


@app.put("/delivery/address", tags=["Customer & Loyalty"])
def update_delivery_address(partner_id: int, address: str, user=Depends(get_current_user)):
    """Updates the customer's address in Odoo"""
    uid, models = get_odoo_models()
    models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'write', [[partner_id], {
        'street': address
    }])
    return {"status": "success", "message": "Address updated"}

@app.get("/delivery/track/{order_id}", tags=["Customer & Loyalty"])
def track_delivery(order_id: int, user=Depends(get_current_user)):
    """Detailed delivery tracking based on POS order state"""
    uid, models = get_odoo_models()
    order = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'pos.order', 'read', [order_id], {'fields': ['state', 'amount_total']})
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Simple status mapping for restaurant delivery
    statuses = {
        'draft': 'Cooking in Kitchen 👨‍🍳',
        'paid': 'Food is Ready! 📦',
        'done': 'Out for Delivery 🛵',
        'invoiced': 'Delivered! Enjoy your meal 🍕'
    }
    
    return {
        "order_id": order_id,
        "status": statuses.get(order[0]['state'], "Processing"),
        "total": order[0]['amount_total']
    }

# --- Customer Support Endpoints (Agent Escalation) ---

@app.post("/support/ticket", tags=["Customer Support"])
def create_support_ticket(ticket: SupportTicket):
    """Creates a support ticket in Odoo. Used by WhatsApp Agent for escalation."""
    uid, models = get_odoo_models()
    
    # 1. Ensure Support Project exists
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'Restaurant Support']]])
    if not project_ids:
        project_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'create', [{'name': 'Restaurant Support'}])
    else:
        project_id = project_ids[0]

    # 2. Create the ticket (Task)
    task_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'create', [{
        'name': f"[{ticket.issue_type}] {ticket.customer_name}",
        'project_id': project_id,
        'description': f"Phone: {ticket.phone}\nIssue: {ticket.message}\nRelated Order ID: {ticket.order_id or 'N/A'}",
        'priority': ticket.priority
    }])
    
    return {"status": "ticket_created", "ticket_id": task_id, "message": "A support agent will follow up shortly."}

@app.get("/support/my-tickets", tags=["Customer Support"])
def list_my_tickets(phone: str):
    """Fetch status of all tickets associated with a phone number"""
    uid, models = get_odoo_models()
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'Restaurant Support']]])
    if not project_ids: return []
    
    tasks = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'search_read',
        [[['project_id', '=', project_ids[0]], ['description', 'ilike', phone]]],
        {'fields': ['id', 'name', 'stage_id', 'create_date']}
    )
    
    return [{
        "ticket_id": t['id'],
        "subject": t['name'],
        "status": t['stage_id'][1] if t.get('stage_id') else "New",
        "created_at": t['create_date']
    } for t in tasks]
