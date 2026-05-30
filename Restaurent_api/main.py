import os
import requests
import datetime
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
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

# --- Sale Order Models (Option A — Customer Delivery Ordering) ---
class SaleOrderItem(BaseModel):
    product_id: int
    quantity: float
    note: Optional[str] = None

class SaleOrderRequest(BaseModel):
    items: List[SaleOrderItem]
    delivery_address: Optional[str] = None  # Street address, falls back to partner's saved address

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

class CustomerProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    email: Optional[str] = None

class RiderRegisterRequest(BaseModel):
    name: str
    phone: str

# Kitchen project name constant
KITCHEN_PROJECT = "Restaurant Kitchen Queue"

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

@app.get("/me/profile", tags=["Customer Profile"])
def get_my_profile(session_id: str = Depends(get_current_session)):
    """Returns the full profile of the currently logged-in customer."""
    uid, partner_id = get_current_user_id(session_id)
    partner = odoo_call_kw('res.partner', 'read', [partner_id],
        {'fields': ['name', 'phone', 'email', 'street', 'city', 'partner_latitude', 'partner_longitude']},
        session_id
    )
    if not partner:
        raise HTTPException(status_code=404, detail="Profile not found")
    p = partner[0]
    return {
        "partner_id": partner_id,
        "name": p.get('name'),
        "phone": p.get('phone'),
        "email": p.get('email'),
        "street": p.get('street'),
        "city": p.get('city'),
        "location": {
            "lat": p.get('partner_latitude'),
            "lng": p.get('partner_longitude')
        }
    }

@app.put("/me/profile", tags=["Customer Profile"])
def update_my_profile(update: CustomerProfileUpdate, session_id: str = Depends(get_current_session)):
    """Updates name, phone, email, or delivery address for the currently logged-in customer."""
    uid, partner_id = get_current_user_id(session_id)
    vals = {k: v for k, v in update.dict().items() if v is not None}
    if not vals:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    odoo_call_kw('res.partner', 'write', [[partner_id], vals], {}, session_id)
    return {"status": "success", "message": "Profile updated successfully", "updated_fields": list(vals.keys())}

@app.post("/customer/logout", tags=["Customer Authentication"])
def customer_logout(session_id: str = Depends(get_current_session)):
    """Invalidates the Odoo session natively. Frontend should discard the session_id after calling this."""
    requests.post(
        f"{ODOO_URL}/web/session/destroy",
        json={"jsonrpc": "2.0", "method": "call", "params": {}},
        cookies={"session_id": session_id}
    )
    return {"status": "success", "message": "Logged out successfully"}

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
    return odoo_call_kw('product.product', 'search_read', domain,
        {'fields': ['id', 'display_name', 'list_price', 'description_sale', 'image_128']},
        session_id
    )

@app.get("/pos/products/{product_id}", tags=["Product Catalog"])
def get_product_detail(product_id: int, session_id: str = Depends(get_current_session)):
    """Returns full product detail for the menu item detail page (image, description, price, combos)."""
    product = odoo_call_kw('product.product', 'read', [product_id],
        {'fields': ['id', 'display_name', 'list_price', 'description_sale', 'image_256', 'pos_categ_ids', 'available_in_pos']},
        session_id
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product[0]

@app.post("/pos/order", tags=["POS Operations (In-Store)"])
def create_pos_order(order: POSOrderRequest, session_id: str = Depends(get_current_session)):
    """For in-store kiosk/cashier use only. Requires an open POS session."""
    sessions = odoo_call_kw('pos.session', 'search_read', [[['state', '=', 'opened']]], {'limit': 1, 'fields': ['id']}, session_id)
    if not sessions:
        raise HTTPException(status_code=400, detail="No open POS session found. Use POST /order for delivery orders.")

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


# ===========================================================================
# --- Option A: Delivery Orders via Sale Order (Customer-Facing Website) ---
# ===========================================================================

@app.post("/order", tags=["Delivery Orders"])
def place_delivery_order(order: SaleOrderRequest, session_id: str = Depends(get_current_session)):
    """
    Places a delivery/takeaway order as a native Odoo Sale Order.
    Works 24/7 — no open POS session required.
    Returns sale_order_id and order_name (e.g. S00042) for tracking.
    """
    uid, partner_id = get_current_user_id(session_id)

    # Optionally update delivery street address
    if order.delivery_address:
        odoo_call_kw('res.partner', 'write', [[partner_id], {'street': order.delivery_address}], {}, session_id)

    # Build Sale Order lines
    order_lines = []
    for item in order.items:
        line = {
            'product_id': item.product_id,
            'product_uom_qty': item.quantity,
        }
        if item.note:
            line['name'] = item.note  # note shows as line description in Odoo
        order_lines.append((0, 0, line))

    sale_order_id = odoo_call_kw('sale.order', 'create', [{
        'partner_id': partner_id,
        'order_line': order_lines,
        'note': 'Placed via Restaurant Delivery App',
    }], {}, session_id)

    # Confirm the order so it flows to the kitchen/delivery
    odoo_call_kw('sale.order', 'action_confirm', [[sale_order_id]], {}, session_id)

    # Fetch order name (e.g. S00042)
    sale_order = odoo_call_kw('sale.order', 'read', [sale_order_id], {'fields': ['name', 'amount_total', 'state']}, session_id)

    # Auto-create a kitchen task so Kitchen Dashboard sees it immediately
    try:
        ensure_kitchen_task(sale_order_id, sale_order[0]['name'], partner_id, session_id)
    except Exception:
        pass  # Kitchen task creation is non-blocking

    return {
        "status": "success",
        "order_id": sale_order_id,
        "order_name": sale_order[0]['name'],
        "total": sale_order[0]['amount_total'],
        "message": "Order confirmed! You can track it via GET /order/{order_id}"
    }


@app.get("/orders/my", tags=["Delivery Orders"])
def my_orders(session_id: str = Depends(get_current_session)):
    """
    Returns the full order history for the currently logged-in customer.
    Each order includes its status and total.
    """
    uid, partner_id = get_current_user_id(session_id)
    orders = odoo_call_kw('sale.order', 'search_read',
        [[['partner_id', '=', partner_id]]],
        {'fields': ['id', 'name', 'date_order', 'amount_total', 'state'], 'order': 'date_order desc'},
        session_id
    )
    STATUS_MAP = {
        'draft': 'Quotation',
        'sent': 'Quotation Sent',
        'sale': 'Order Confirmed',
        'done': 'Order Delivered',
        'cancel': 'Cancelled',
    }
    return [{
        "order_id": o['id'],
        "order_name": o['name'],
        "date": o['date_order'],
        "total": o['amount_total'],
        "status": STATUS_MAP.get(o['state'], o['state'])
    } for o in orders]


@app.get("/order/{order_id}", tags=["Delivery Orders"])
def get_order_detail(order_id: int, session_id: str = Depends(get_current_session)):
    """
    Returns full details of a specific sale order including:
    - Order lines (items ordered)
    - Delivery status from the linked stock picking
    - Rider/carrier tracking info
    """
    # 1. Fetch Sale Order
    sale_order = odoo_call_kw('sale.order', 'read', [order_id],
        {'fields': ['name', 'date_order', 'amount_total', 'state', 'order_line', 'picking_ids', 'partner_id']},
        session_id
    )
    if not sale_order:
        raise HTTPException(status_code=404, detail="Order not found")
    so = sale_order[0]

    # 2. Fetch Order Lines
    lines = []
    if so.get('order_line'):
        line_data = odoo_call_kw('sale.order.line', 'read', [so['order_line']],
            {'fields': ['product_id', 'product_uom_qty', 'price_subtotal', 'name']},
            session_id
        )
        lines = [{
            "product": l['product_id'][1] if l.get('product_id') else 'Unknown',
            "quantity": l['product_uom_qty'],
            "subtotal": l['price_subtotal'],
            "note": l.get('name', '')
        } for l in line_data]

    # 3. Fetch Delivery (stock.picking) status
    delivery_info = None
    DELIVERY_STATUS_MAP = {
        'draft': 'Preparing',
        'waiting': 'Waiting for Stock',
        'confirmed': 'Order Confirmed',
        'assigned': 'Ready — Out for Delivery 🛵',
        'done': 'Delivered ✅',
        'cancel': 'Cancelled',
    }
    if so.get('picking_ids'):
        picking = odoo_call_kw('stock.picking', 'read', [so['picking_ids'][0]],
            {'fields': ['name', 'state', 'scheduled_date', 'carrier_tracking_ref']},
            session_id
        )
        if picking:
            delivery_info = {
                "delivery_ref": picking[0]['name'],
                "status": DELIVERY_STATUS_MAP.get(picking[0]['state'], picking[0]['state']),
                "scheduled_date": picking[0].get('scheduled_date'),
                "tracking_ref": picking[0].get('carrier_tracking_ref'),
            }

    STATUS_MAP = {
        'draft': 'Quotation', 'sent': 'Quotation Sent', 'sale': 'Confirmed',
        'done': 'Delivered', 'cancel': 'Cancelled'
    }
    return {
        "order_id": order_id,
        "order_name": so['name'],
        "date": so['date_order'],
        "total": so['amount_total'],
        "status": STATUS_MAP.get(so['state'], so['state']),
        "items": lines,
        "delivery": delivery_info
    }

@app.post("/order/{order_id}/cancel", tags=["Delivery Orders"])
def cancel_order(order_id: int, session_id: str = Depends(get_current_session)):
    """
    Cancels a delivery Sale Order if it has not yet been shipped.
    Odoo natively blocks cancellation of orders already in delivery — returns 403 if so.
    """
    # Verify order belongs to this customer
    uid, partner_id = get_current_user_id(session_id)
    sale_order = odoo_call_kw('sale.order', 'read', [order_id],
        {'fields': ['state', 'partner_id', 'name']},
        session_id
    )
    if not sale_order:
        raise HTTPException(status_code=404, detail="Order not found")
    so = sale_order[0]
    if so['partner_id'][0] != partner_id:
        raise HTTPException(status_code=403, detail="You can only cancel your own orders")
    if so['state'] in ('done', 'cancel'):
        raise HTTPException(status_code=400, detail=f"Order cannot be cancelled — current status: {so['state']}")

    # Native Odoo cancel action
    odoo_call_kw('sale.order', 'action_cancel', [[order_id]], {}, session_id)
    return {"status": "cancelled", "order_name": so['name'], "message": "Order cancelled successfully"}


@app.post("/order/{order_id}/reorder", tags=["Delivery Orders"])
def reorder(order_id: int, session_id: str = Depends(get_current_session)):
    """
    Re-places the exact same items from a previous order as a new Sale Order.
    Useful for repeat customers.
    """
    uid, partner_id = get_current_user_id(session_id)
    # Fetch original order lines
    original = odoo_call_kw('sale.order', 'read', [order_id],
        {'fields': ['order_line', 'partner_id']},
        session_id
    )
    if not original:
        raise HTTPException(status_code=404, detail="Original order not found")
    if original[0]['partner_id'][0] != partner_id:
        raise HTTPException(status_code=403, detail="You can only reorder your own orders")

    line_data = odoo_call_kw('sale.order.line', 'read', [original[0]['order_line']],
        {'fields': ['product_id', 'product_uom_qty']},
        session_id
    )
    new_lines = [(0, 0, {'product_id': l['product_id'][0], 'product_uom_qty': l['product_uom_qty']}) for l in line_data if l.get('product_id')]
    if not new_lines:
        raise HTTPException(status_code=400, detail="No valid lines found in the original order")

    new_order_id = odoo_call_kw('sale.order', 'create', [{
        'partner_id': partner_id,
        'order_line': new_lines,
        'note': f'Re-order of SO#{order_id} via Restaurant App',
    }], {}, session_id)
    odoo_call_kw('sale.order', 'action_confirm', [[new_order_id]], {}, session_id)
    new_order = odoo_call_kw('sale.order', 'read', [new_order_id], {'fields': ['name', 'amount_total']}, session_id)
    return {
        "status": "success",
        "order_id": new_order_id,
        "order_name": new_order[0]['name'],
        "total": new_order[0]['amount_total'],
        "message": "Reorder placed successfully!"
    }


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

# ===========================================================================
# --- Dashboard Helpers ---
# ===========================================================================

def get_rider_tag(session_id):
    tag_ids = odoo_call_kw('res.partner.category', 'search', [[['name', '=', 'Rider']]], {}, session_id)
    if not tag_ids:
        return odoo_call_kw('res.partner.category', 'create', [{'name': 'Rider'}], {}, session_id)
    return tag_ids[0]

def get_or_create_stage(stage_name, project_id, session_id):
    stage_ids = odoo_call_kw('project.task.type', 'search',
        [[['name', '=', stage_name], ['project_ids', 'in', [project_id]]]], {}, session_id)
    if not stage_ids:
        return odoo_call_kw('project.task.type', 'create',
            [{'name': stage_name, 'project_ids': [(4, project_id)]}], {}, session_id)
    return stage_ids[0]

def get_kitchen_project(session_id):
    ids = odoo_call_kw('project.project', 'search', [[['name', '=', KITCHEN_PROJECT]]], {}, session_id)
    if not ids:
        return odoo_call_kw('project.project', 'create', [{'name': KITCHEN_PROJECT}], {}, session_id)
    return ids[0]

def ensure_kitchen_task(order_id, order_name, partner_id, session_id):
    """Creates a kitchen queue task when an order is confirmed."""
    project_id = get_kitchen_project(session_id)
    existing = odoo_call_kw('project.task', 'search',
        [[['project_id', '=', project_id], ['description', 'ilike', f'SALE_ORDER_ID:{order_id}']]], {}, session_id)
    if existing:
        return existing[0]
    stage_id = get_or_create_stage("Received", project_id, session_id)
    return odoo_call_kw('project.task', 'create', [{
        'name': f'Order {order_name}',
        'project_id': project_id,
        'stage_id': stage_id,
        'partner_id': partner_id,
        'description': f'SALE_ORDER_ID:{order_id}'
    }], {}, session_id)

# ===========================================================================
# --- ADMIN DASHBOARD ---
# ===========================================================================

@app.get("/admin/dashboard", tags=["Admin Dashboard"])
def admin_dashboard(session_id: str = Depends(get_current_session)):
    """Admin overview: orders today, revenue today, active riders, kitchen queue depth."""
    today = datetime.date.today().strftime('%Y-%m-%d')
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    orders_today = odoo_call_kw('sale.order', 'search_read',
        [[['state', 'in', ['sale', 'done']], ['date_order', '>=', today], ['date_order', '<', tomorrow]]],
        {'fields': ['amount_total']}, session_id)
    revenue_today = round(sum(o['amount_total'] for o in orders_today), 2) if orders_today else 0.0
    rider_tag = get_rider_tag(session_id)
    active_riders = odoo_call_kw('res.partner', 'search_count', [[['category_id', 'in', [rider_tag]]]], {}, session_id)
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', KITCHEN_PROJECT]]], {}, session_id)
    kitchen_pending = odoo_call_kw('project.task', 'search_count',
        [[['project_id', '=', project_ids[0]], ['stage_id.name', 'not in', ['Delivered']]]], {}, session_id) if project_ids else 0
    return {"orders_today": len(orders_today), "revenue_today": revenue_today,
            "active_riders": active_riders, "kitchen_queue_depth": kitchen_pending}

@app.get("/admin/orders", tags=["Admin Dashboard"])
def admin_list_orders(status: Optional[str] = None, date_from: Optional[str] = None,
                      date_to: Optional[str] = None, limit: int = 50,
                      session_id: str = Depends(get_current_session)):
    """All orders with optional filters by status and date range."""
    domain = []
    if status: domain.append(['state', '=', status])
    if date_from: domain.append(['date_order', '>=', date_from])
    if date_to: domain.append(['date_order', '<=', date_to + ' 23:59:59'])
    orders = odoo_call_kw('sale.order', 'search_read', [domain],
        {'fields': ['id', 'name', 'date_order', 'amount_total', 'state', 'partner_id'],
         'limit': limit, 'order': 'date_order desc'}, session_id)
    STATUS_MAP = {'draft': 'New', 'sale': 'Confirmed', 'done': 'Delivered', 'cancel': 'Cancelled'}
    return [{"order_id": o['id'], "order_name": o['name'],
             "customer": o['partner_id'][1] if o.get('partner_id') else "Unknown",
             "date": o['date_order'], "total": o['amount_total'],
             "status": STATUS_MAP.get(o['state'], o['state'])} for o in orders]

@app.get("/admin/riders", tags=["Admin Dashboard"])
def list_riders(session_id: str = Depends(get_current_session)):
    """All registered riders with their last known GPS location."""
    rider_tag = get_rider_tag(session_id)
    riders = odoo_call_kw('res.partner', 'search_read', [[['category_id', 'in', [rider_tag]]]],
        {'fields': ['id', 'name', 'phone', 'partner_latitude', 'partner_longitude']}, session_id)
    return [{"rider_id": r['id'], "name": r['name'], "phone": r.get('phone'),
             "last_location": {"lat": r.get('partner_latitude'), "lng": r.get('partner_longitude')}} for r in riders]

@app.post("/admin/riders", tags=["Admin Dashboard"])
def register_rider(req: RiderRegisterRequest, session_id: str = Depends(get_current_session)):
    """Register a new delivery rider as a tagged Odoo partner."""
    rider_tag = get_rider_tag(session_id)
    partner_id = odoo_call_kw('res.partner', 'create',
        [{'name': req.name, 'phone': req.phone, 'category_id': [(4, rider_tag)]}], {}, session_id)
    return {"status": "success", "rider_id": partner_id, "message": f"Rider '{req.name}' registered"}

# ===========================================================================
# --- MANAGER DASHBOARD ---
# ===========================================================================

@app.get("/manager/orders/pending", tags=["Manager Dashboard"])
def manager_pending_orders(session_id: str = Depends(get_current_session)):
    """Orders confirmed but not yet delivered. Manager review queue."""
    orders = odoo_call_kw('sale.order', 'search_read', [[['state', '=', 'sale']]],
        {'fields': ['id', 'name', 'date_order', 'amount_total', 'partner_id', 'picking_ids'],
         'order': 'date_order asc'}, session_id)
    result = []
    for o in orders:
        delivery_state = "pending"
        if o.get('picking_ids'):
            picking = odoo_call_kw('stock.picking', 'read', [o['picking_ids'][0]], {'fields': ['state']}, session_id)
            if picking: delivery_state = picking[0]['state']
        result.append({"order_id": o['id'], "order_name": o['name'],
                        "customer": o['partner_id'][1] if o.get('partner_id') else "Unknown",
                        "date": o['date_order'], "total": o['amount_total'], "delivery_state": delivery_state})
    return result

@app.get("/manager/revenue", tags=["Manager Dashboard"])
def manager_revenue(session_id: str = Depends(get_current_session)):
    """Revenue breakdown: today, this week, this month."""
    today = datetime.date.today()
    week_start = (today - datetime.timedelta(days=today.weekday())).strftime('%Y-%m-%d')
    month_start = today.replace(day=1).strftime('%Y-%m-%d')
    today_str, tomorrow_str = today.strftime('%Y-%m-%d'), (today + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    def get_rev(d_from, d_to):
        rows = odoo_call_kw('sale.order', 'search_read',
            [[['state', 'in', ['sale', 'done']], ['date_order', '>=', d_from], ['date_order', '<', d_to]]],
            {'fields': ['amount_total']}, session_id)
        return round(sum(r['amount_total'] for r in rows), 2) if rows else 0.0
    return {"today": get_rev(today_str, tomorrow_str), "this_week": get_rev(week_start, tomorrow_str),
            "this_month": get_rev(month_start, tomorrow_str),
            "orders_today": odoo_call_kw('sale.order', 'search_count',
                [[['state', 'in', ['sale', 'done']], ['date_order', '>=', today_str], ['date_order', '<', tomorrow_str]]],
                {}, session_id)}

# ===========================================================================
# --- KITCHEN DASHBOARD ---
# ===========================================================================

@app.get("/kitchen/queue", tags=["Kitchen Dashboard"])
def kitchen_queue(session_id: str = Depends(get_current_session)):
    """All active orders in the kitchen queue with items. Excludes Picked Up and Delivered."""
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', KITCHEN_PROJECT]]], {}, session_id)
    if not project_ids: return []
    tasks = odoo_call_kw('project.task', 'search_read',
        [[['project_id', '=', project_ids[0]], ['stage_id.name', 'not in', ['Picked Up', 'Delivered']]]],
        {'fields': ['id', 'name', 'stage_id', 'description', 'partner_id', 'create_date'], 'order': 'create_date asc'},
        session_id)
    result = []
    for task in tasks:
        order_id, items = None, []
        desc = task.get('description', '')
        if 'SALE_ORDER_ID:' in desc:
            try: order_id = int(desc.split('SALE_ORDER_ID:')[1].split('\n')[0].strip())
            except ValueError: pass
        if order_id:
            lines = odoo_call_kw('sale.order.line', 'search_read', [[['order_id', '=', order_id]]],
                {'fields': ['product_id', 'product_uom_qty', 'name']}, session_id)
            items = [{"product": l['product_id'][1], "qty": l['product_uom_qty'], "note": l.get('name', '')}
                     for l in lines if l.get('product_id')]
        result.append({"task_id": task['id'], "order_id": order_id, "order_name": task['name'],
                        "customer": task['partner_id'][1] if task.get('partner_id') else "Unknown",
                        "status": task['stage_id'][1] if task.get('stage_id') else "Received",
                        "received_at": task['create_date'], "items": items})
    return result

@app.post("/kitchen/order/{order_id}/ready", tags=["Kitchen Dashboard"])
def kitchen_order_ready(order_id: int, session_id: str = Depends(get_current_session)):
    """Kitchen marks an order ready for rider pickup."""
    so = odoo_call_kw('sale.order', 'read', [order_id], {'fields': ['name']}, session_id)
    if not so: raise HTTPException(status_code=404, detail="Order not found")
    project_id = get_kitchen_project(session_id)
    stage_id = get_or_create_stage("Ready for Pickup", project_id, session_id)
    tasks = odoo_call_kw('project.task', 'search',
        [[['project_id', '=', project_id], ['description', 'ilike', f'SALE_ORDER_ID:{order_id}']]], {}, session_id)
    if not tasks: raise HTTPException(status_code=404, detail="No kitchen task found. Was order placed via POST /order?")
    odoo_call_kw('project.task', 'write', [[tasks[0]], {'stage_id': stage_id}], {}, session_id)
    odoo_call_kw('sale.order', 'message_post', [[order_id]],
        {'body': '🍽️ Order is ready for pickup!', 'message_type': 'comment'}, session_id)
    return {"status": "ready", "order_id": order_id, "order_name": so[0]['name']}

# ===========================================================================
# --- RIDER DASHBOARD ---
# ===========================================================================

@app.get("/rider/jobs", tags=["Rider Dashboard"])
def rider_jobs(session_id: str = Depends(get_current_session)):
    """All delivery jobs assigned to the logged-in rider."""
    uid, partner_id = get_current_user_id(session_id)
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'Food Deliveries']]], {}, session_id)
    if not project_ids: return []
    tasks = odoo_call_kw('project.task', 'search_read',
        [[['project_id', '=', project_ids[0]], ['description', 'ilike', f'RIDER_PARTNER_ID:{partner_id}']]],
        {'fields': ['id', 'name', 'stage_id', 'description', 'partner_id']}, session_id)
    result = []
    for task in tasks:
        order_id, cust_loc = None, None
        desc = task.get('description', '')
        if 'ORDER_ID:' in desc:
            try: order_id = int(desc.split('ORDER_ID:')[1].split('\n')[0].strip())
            except ValueError: pass
        if task.get('partner_id'):
            p = odoo_call_kw('res.partner', 'read', [task['partner_id'][0]],
                {'fields': ['street', 'city', 'partner_latitude', 'partner_longitude']}, session_id)
            if p:
                cust_loc = {"address": f"{p[0].get('street','')}, {p[0].get('city','')}",
                            "lat": p[0].get('partner_latitude'), "lng": p[0].get('partner_longitude')}
        result.append({"task_id": task['id'], "order_id": order_id, "order_name": task['name'],
                        "status": task['stage_id'][1] if task.get('stage_id') else "Assigned",
                        "customer_location": cust_loc})
    return result

@app.post("/rider/order/{order_id}/picked_up", tags=["Rider Dashboard"])
def rider_picked_up(order_id: int, session_id: str = Depends(get_current_session)):
    """Rider confirms pickup from kitchen. Moves task to Picked Up stage."""
    project_id = get_kitchen_project(session_id)
    stage_id = get_or_create_stage("Picked Up", project_id, session_id)
    tasks = odoo_call_kw('project.task', 'search',
        [[['project_id', '=', project_id], ['description', 'ilike', f'SALE_ORDER_ID:{order_id}']]], {}, session_id)
    if tasks: odoo_call_kw('project.task', 'write', [[tasks[0]], {'stage_id': stage_id}], {}, session_id)
    odoo_call_kw('sale.order', 'message_post', [[order_id]],
        {'body': '🛵 Order picked up. Rider on the way!', 'message_type': 'comment'}, session_id)
    return {"status": "picked_up", "order_id": order_id}

@app.post("/rider/order/{order_id}/delivered", tags=["Rider Dashboard"])
def rider_delivered(order_id: int, session_id: str = Depends(get_current_session)):
    """Rider confirms delivery. Validates stock.picking natively in Odoo."""
    project_id = get_kitchen_project(session_id)
    stage_id = get_or_create_stage("Delivered", project_id, session_id)
    tasks = odoo_call_kw('project.task', 'search',
        [[['project_id', '=', project_id], ['description', 'ilike', f'SALE_ORDER_ID:{order_id}']]], {}, session_id)
    if tasks: odoo_call_kw('project.task', 'write', [[tasks[0]], {'stage_id': stage_id}], {}, session_id)
    so = odoo_call_kw('sale.order', 'read', [order_id], {'fields': ['picking_ids']}, session_id)
    if so and so[0].get('picking_ids'):
        for pid in so[0]['picking_ids']:
            picking = odoo_call_kw('stock.picking', 'read', [pid], {'fields': ['state']}, session_id)
            if picking and picking[0]['state'] == 'assigned':
                try: odoo_call_kw('stock.picking', 'button_validate', [[pid]], {}, session_id)
                except Exception: pass
    odoo_call_kw('sale.order', 'message_post', [[order_id]],
        {'body': '✅ Delivered to customer!', 'message_type': 'comment'}, session_id)
    return {"status": "delivered", "order_id": order_id,
            "message": "Delivery confirmed. Fetch receipt via GET /order/{id}/receipt"}

# ===========================================================================
# --- RECEIPT & INVOICE ---
# ===========================================================================

@app.get("/order/{order_id}/receipt", tags=["Receipt & Invoice"])
def get_receipt(order_id: int, session_id: str = Depends(get_current_session)):
    """Returns a structured receipt payload ready for frontend print rendering."""
    so = odoo_call_kw('sale.order', 'read', [order_id],
        {'fields': ['name', 'date_order', 'amount_total', 'amount_tax', 'partner_id', 'order_line', 'state', 'note']},
        session_id)
    if not so: raise HTTPException(status_code=404, detail="Order not found")
    o = so[0]
    lines = []
    if o.get('order_line'):
        ld = odoo_call_kw('sale.order.line', 'read', [o['order_line']],
            {'fields': ['product_id', 'product_uom_qty', 'price_unit', 'price_subtotal', 'name']}, session_id)
        lines = [{"product": l['product_id'][1] if l.get('product_id') else "Unknown",
                  "qty": l['product_uom_qty'], "unit_price": l['price_unit'],
                  "subtotal": l['price_subtotal'], "note": l.get('name', '')} for l in ld]
    customer = {}
    if o.get('partner_id'):
        p = odoo_call_kw('res.partner', 'read', [o['partner_id'][0]],
            {'fields': ['name', 'phone', 'street', 'city']}, session_id)
        if p: customer = {"name": p[0]['name'], "phone": p[0].get('phone'),
                           "address": f"{p[0].get('street','')}, {p[0].get('city','')}"}
    return {"receipt": {"order_ref": o['name'], "date": o['date_order'], "status": o['state'],
                         "customer": customer, "items": lines,
                         "subtotal": round(o['amount_total'] - o['amount_tax'], 2),
                         "tax": o['amount_tax'], "total": o['amount_total'], "note": o.get('note', '')}}

@app.post("/order/{order_id}/invoice", tags=["Receipt & Invoice"])
def create_invoice(order_id: int, session_id: str = Depends(get_current_session)):
    """Creates a native Odoo Invoice (account.move) from the confirmed Sale Order."""
    so = odoo_call_kw('sale.order', 'read', [order_id], {'fields': ['state', 'name', 'invoice_ids']}, session_id)
    if not so: raise HTTPException(status_code=404, detail="Order not found")
    if so[0]['state'] not in ('sale', 'done'):
        raise HTTPException(status_code=400, detail="Order must be confirmed before invoicing")
    if so[0].get('invoice_ids'):
        return {"status": "already_invoiced", "invoice_ids": so[0]['invoice_ids']}
    result = odoo_call_kw('sale.order', 'action_invoice_create', [[order_id]], {}, session_id)
    return {"status": "invoiced", "order_name": so[0]['name'],
            "message": "Invoice created. View in Odoo Accounting > Customer Invoices."}


