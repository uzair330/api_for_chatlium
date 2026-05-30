import os
import requests
import datetime
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Odoo Configuration
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")

app = FastAPI(title="Odoo Restaurant POS API")
security = HTTPBearer()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Models ---
class Token(BaseModel):
    session_id: str
    token_type: str

class LoginRequest(BaseModel):
    username: str
    password: str

class CustomerLoginRequest(BaseModel):
    phone: str
    password: str

class CustomerRegisterRequest(BaseModel):
    name: str
    phone: str
    password: str

class POSOrderItem(BaseModel):
    product_id: int
    quantity: float
    combo_choices: Optional[List[int]] = None
    note: Optional[str] = None

class POSOrderRequest(BaseModel):
    partner_id: int
    items: List[POSOrderItem]

class LocationRequest(BaseModel):
    latitude: float
    longitude: float

class RiderAssignRequest(BaseModel):
    rider_partner_id: int

class SupportTicket(BaseModel):
    customer_name: str
    phone: str
    issue_type: str
    message: str
    priority: str = "0"
    order_id: Optional[int] = None

# --- Native Odoo Auth Helpers ---
def get_current_session(auth: HTTPAuthorizationCredentials = Security(security)):
    """Extracts the Odoo session_id passed in the Authorization Bearer header"""
    return auth.credentials

def get_current_user_id(session_id: str):
    """Fetches the user_id (uid) and partner_id of the current session"""
    res = requests.post(
        f"{ODOO_URL}/web/session/get_session_info", 
        json={"jsonrpc": "2.0", "method": "call", "params": {}}, 
        cookies={"session_id": session_id}
    )
    data = res.json().get("result", {})
    if not data.get("uid"):
        raise HTTPException(status_code=401, detail="Invalid session")
    return data.get("uid"), data.get("partner_id")

def odoo_call_kw(model, method, args=[], kwargs={}, session_id=None):
    """Executes a JSON-RPC call to Odoo using the user's native session"""
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "model": model,
            "method": method,
            "args": args,
            "kwargs": kwargs
        }
    }
    cookies = {"session_id": session_id} if session_id else {}
    try:
        res = requests.post(f"{ODOO_URL}/web/dataset/call_kw", json=payload, cookies=cookies)
        res_data = res.json()
        if "error" in res_data:
            err_msg = res_data["error"].get("data", {}).get("message", "Access Denied by Odoo")
            logger.error(f"Odoo Access Error: {err_msg}")
            raise HTTPException(status_code=403, detail=err_msg)
        return res_data.get("result")
    except requests.exceptions.RequestException as e:
        logger.error(f"Odoo Connection Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error communicating with Odoo")

# --- Endpoints ---

@app.post("/login", response_model=Token, tags=["Authentication"])
def login(req: LoginRequest):
    """Authenticates natively against Odoo and returns the Odoo session_id"""
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "db": ODOO_DB,
            "login": req.username,
            "password": req.password
        }
    }
    res = requests.post(f"{ODOO_URL}/web/session/authenticate", json=payload)
    res_data = res.json()
    
    if "error" in res_data or not res_data.get("result", {}).get("uid"):
        raise HTTPException(status_code=401, detail="Invalid Odoo credentials")
        
    session_id = res.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=500, detail="Odoo did not return a session_id")
        
    return {"session_id": session_id, "token_type": "bearer"}

@app.post("/customer/register", tags=["Customer Authentication"])
def register_customer(req: CustomerRegisterRequest):
    """Creates a new Customer (Portal User) in Odoo so they can login natively."""
    admin_payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {"db": ODOO_DB, "login": os.getenv("ODOO_USER", "admin"), "password": os.getenv("ODOO_PASSWORD", "admin")}
    }
    admin_res = requests.post(f"{ODOO_URL}/web/session/authenticate", json=admin_payload)
    admin_session_id = admin_res.cookies.get("session_id")
    if not admin_session_id:
        raise HTTPException(status_code=500, detail="Failed to authenticate admin server-side")

    groups = odoo_call_kw('res.groups', 'search', [[['name', 'ilike', 'Portal']]], {}, admin_session_id)
    group_id = groups[0] if groups else None

    user_vals = {
        'name': req.name,
        'login': req.phone,  # Use phone as login
        'password': req.password,
        'phone': req.phone,
    }

    try:
        # Create user without groups_id first to avoid ValueError
        user_id = odoo_call_kw('res.users', 'create', [user_vals], {}, admin_session_id)
        
        # Try to assign portal group via write, ignore if field doesn't exist
        if group_id:
            try:
                odoo_call_kw('res.users', 'write', [[user_id], {'groups_id': [(4, group_id)]}], {}, admin_session_id)
            except Exception:
                pass
                
    except HTTPException as e:
        if "Duplicate" in str(e.detail) or "already exists" in str(e.detail):
            raise HTTPException(status_code=400, detail="Phone number already registered.")
        raise e

    return {"status": "success", "user_id": user_id, "message": "Customer registered successfully. You can now login via /customer/login."}

@app.post("/customer/login", response_model=Token, tags=["Customer Authentication"])
def customer_login(req: CustomerLoginRequest):
    """Customer login expects the phone number (login) and password."""
    # Under the hood, this is the exact same native Odoo session authentication as /login
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "db": ODOO_DB,
            "login": req.phone,  # login is the phone number
            "password": req.password
        }
    }
    res = requests.post(f"{ODOO_URL}/web/session/authenticate", json=payload)
    res_data = res.json()
    
    if "error" in res_data or not res_data.get("result", {}).get("uid"):
        raise HTTPException(status_code=401, detail="Invalid phone number or password")
        
    session_id = res.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=500, detail="Odoo did not return a session_id")
        
    return {"session_id": session_id, "token_type": "bearer"}

@app.get("/me", tags=["Authentication"])
def get_me(session_id: str = Depends(get_current_session)):
    """Verifies the session and returns user info using native Odoo session"""
    uid, partner_id = get_current_user_id(session_id)
    return {"uid": uid, "partner_id": partner_id}

@app.put("/me/location", tags=["Delivery & Tracking"])
def update_my_location(loc: LocationRequest, session_id: str = Depends(get_current_session)):
    """Updates the latitude/longitude for the currently authenticated user/rider"""
    uid, partner_id = get_current_user_id(session_id)
    # Using partner_latitude and partner_longitude. Ensure Odoo base_geolocalize is installed if these throw an error.
    try:
        odoo_call_kw('res.partner', 'write', [[partner_id], {
            'partner_latitude': loc.latitude, 
            'partner_longitude': loc.longitude
        }], {}, session_id)
        return {"status": "success", "message": "Location updated successfully"}
    except Exception as e:
        logger.error(f"Error updating geolocation (is base_geolocalize module installed in Odoo?): {e}")
        raise HTTPException(status_code=400, detail="Could not update geolocation. Ensure 'Partner Geolocation' app is installed in Odoo.")

@app.get("/pos/categories", tags=["POS Operations"])
def get_categories(session_id: str = Depends(get_current_session)):
    return odoo_call_kw('pos.category', 'search_read', [], {'fields': ['id', 'name']}, session_id)

@app.get("/pos/products", tags=["Product Catalog"])
def get_products(category_id: Optional[int] = None, session_id: str = Depends(get_current_session)):
    domain = [[['available_in_pos', '=', True]]]
    if category_id:
        domain[0].append(['pos_categ_ids', 'in', [category_id]])
    return odoo_call_kw('product.product', 'search_read', domain, {'fields': ['id', 'display_name', 'list_price']}, session_id)

@app.post("/pos/order", tags=["POS Operations"])
def create_order(order: POSOrderRequest, session_id: str = Depends(get_current_session)):
    sessions = odoo_call_kw('pos.session', 'search_read', [[['state', '=', 'opened']]], {'limit': 1, 'fields': ['id']}, session_id)
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
        if item.note: line['note'] = item.note
        if item.combo_choices:
            line['combo_line_ids'] = [(4, choice_id) for choice_id in item.combo_choices]
        order_payload['lines'].append((0, 0, line))

    order_id = odoo_call_kw('pos.order', 'create', [order_payload], {}, session_id)
    return {"status": "success", "order_id": order_id}

@app.post("/delivery/{order_id}/assign_rider", tags=["Delivery & Tracking"])
def assign_rider_to_order(order_id: int, req: RiderAssignRequest, session_id: str = Depends(get_current_session)):
    """Assigns a rider to an order by creating a Delivery Task in Odoo's Project app natively"""
    # Verify order exists
    order = odoo_call_kw('pos.order', 'read', [order_id], {'fields': ['name', 'partner_id']}, session_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")

    # Find or create a Deliveries project
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'Food Deliveries']]], {}, session_id)
    if not project_ids:
        project_id = odoo_call_kw('project.project', 'create', [{'name': 'Food Deliveries'}], {}, session_id)
    else:
        project_id = project_ids[0]

    # Create Delivery Task and assign Rider
    task_id = odoo_call_kw('project.task', 'create', [{
        'name': f"Delivery for {order[0]['name']} (Order #{order_id})",
        'project_id': project_id,
        'partner_id': order[0]['partner_id'][0] if order[0]['partner_id'] else False,
        'description': f"Link: {order_id}",
        # In Odoo 16+, user_ids is the assignee. Since riders might only be partners in our setup, 
        # let's just log them in the description or a custom tag to avoid complex HR/User logic for now.
        # But wait, we can assign tags. Let's just create it and tag it with the rider's name.
    }], {}, session_id)

    # Note: Odoo tasks usually assign to res.users, not res.partner. 
    # To keep it completely standard, we store the rider's partner_id in the task description to parse it back.
    odoo_call_kw('project.task', 'write', [[task_id], {
        'description': f"ORDER_ID:{order_id}\nRIDER_PARTNER_ID:{req.rider_partner_id}"
    }], {}, session_id)

    return {"status": "success", "task_id": task_id, "message": f"Rider assigned to order {order_id}"}

@app.get("/delivery/track/{order_id}", tags=["Delivery & Tracking"])
def track_delivery(order_id: int, session_id: str = Depends(get_current_session)):
    """Comprehensive tracking endpoint returning Order Status, Customer Lat/Long, and Rider Lat/Long for Map rendering."""
    # 1. Get Order details
    order = odoo_call_kw('pos.order', 'read', [order_id], {'fields': ['state', 'amount_total', 'partner_id']}, session_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    
    response = {
        "order_id": order_id,
        "status": order[0]['state'],
        "total": order[0]['amount_total'],
        "customer_location": None,
        "rider_location": None,
        "rider_assigned": False
    }

    # 2. Get Customer Location
    if order[0].get('partner_id'):
        customer_id = order[0]['partner_id'][0]
        customer = odoo_call_kw('res.partner', 'read', [customer_id], {'fields': ['partner_latitude', 'partner_longitude']}, session_id)
        if customer and customer[0].get('partner_latitude'):
            response["customer_location"] = {
                "lat": customer[0]['partner_latitude'],
                "lng": customer[0]['partner_longitude']
            }

    # 3. Check for Delivery Task (to find assigned Rider)
    tasks = odoo_call_kw('project.task', 'search_read', [[['name', 'ilike', f"Order #{order_id}"]]], {'fields': ['description']}, session_id)
    if tasks and tasks[0].get('description'):
        desc = tasks[0]['description']
        # Extract RIDER_PARTNER_ID from description block
        if "RIDER_PARTNER_ID:" in desc:
            rider_id_str = desc.split("RIDER_PARTNER_ID:")[1].split("\n")[0].strip()
            try:
                rider_id = int(rider_id_str)
                rider = odoo_call_kw('res.partner', 'read', [rider_id], {'fields': ['name', 'partner_latitude', 'partner_longitude', 'phone']}, session_id)
                if rider:
                    response["rider_assigned"] = True
                    response["rider_details"] = {"name": rider[0]['name'], "phone": rider[0].get('phone')}
                    if rider[0].get('partner_latitude'):
                        response["rider_location"] = {
                            "lat": rider[0]['partner_latitude'],
                            "lng": rider[0]['partner_longitude']
                        }
            except ValueError:
                pass

    return response

@app.get("/pos/combos", tags=["Product Catalog"])
def get_combos(session_id: str = Depends(get_current_session)):
    return odoo_call_kw('product.product', 'search_read', [[['available_in_pos', '=', True], ['type', '=', 'combo']]], {'fields': ['id', 'display_name', 'list_price']}, session_id)

@app.get("/pos/combos/{product_id}/choices", tags=["Product Catalog"])
def get_combo_choices(product_id: int, session_id: str = Depends(get_current_session)):
    product = odoo_call_kw('product.product', 'read', [product_id], {'fields': ['combo_ids']}, session_id)
    if not product or not product[0].get('combo_ids'):
        raise HTTPException(status_code=404, detail="No combo choices found for this product")

    combos = odoo_call_kw('pos.combo', 'read', [product[0]['combo_ids']], {'fields': ['id', 'name', 'combo_line_ids']}, session_id)
    
    result = []
    for combo in combos:
        lines = odoo_call_kw('pos.combo.line', 'read', [combo['combo_line_ids']], {'fields': ['product_id', 'extra_price']}, session_id)
        result.append({
            "combo_id": combo['id'],
            "name": combo['name'],
            "choices": [{"id": l['product_id'][0], "name": l['product_id'][1], "extra_price": l['extra_price']} for l in lines]
        })
    return result

@app.get("/customer/loyalty", tags=["Customer & Loyalty"])
def get_loyalty_points(partner_id: int, session_id: str = Depends(get_current_session)):
    cards = odoo_call_kw('loyalty.card', 'search_read', [[['partner_id', '=', partner_id]]], {'fields': ['points', 'program_id', 'code']}, session_id)
    if not cards: return {"points": 0, "rewards": [], "message": "No loyalty card found"}

    program_ids = [c['program_id'][0] for c in cards]
    rewards = odoo_call_kw('loyalty.reward', 'search_read', [[['program_id', 'in', program_ids]]], {'fields': ['id', 'description', 'required_points']}, session_id)

    return {
        "points": sum(c['points'] for c in cards),
        "card_codes": [c['code'] for c in cards],
        "available_rewards": rewards
    }

@app.post("/support/ticket", tags=["Customer Support"])
def create_support_ticket(ticket: SupportTicket, session_id: str = Depends(get_current_session)):
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'Restaurant Support']]], {}, session_id)
    if not project_ids:
        project_id = odoo_call_kw('project.project', 'create', [{'name': 'Restaurant Support'}], {}, session_id)
    else:
        project_id = project_ids[0]

    task_id = odoo_call_kw('project.task', 'create', [{
        'name': f"[{ticket.issue_type}] {ticket.customer_name}",
        'project_id': project_id,
        'description': f"Phone: {ticket.phone}\nIssue: {ticket.message}\nRelated Order ID: {ticket.order_id or 'N/A'}",
        'priority': ticket.priority
    }], {}, session_id)
    return {"status": "ticket_created", "ticket_id": task_id, "message": "A support agent will follow up shortly."}
