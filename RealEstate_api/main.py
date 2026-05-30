import os
import xmlrpc.client
import jwt
import datetime
import logging
import re
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, Security, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Real Estate Management API", version="1.0.0", description="Odoo-Integrated Property & Real Estate API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")
JWT_SECRET = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

# ===========================================================================
# --- Pydantic Models ---
# ===========================================================================

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class LoginRequest(BaseModel):
    username: str
    password: str

class Property(BaseModel):
    id: Optional[int] = None
    name: str
    price: float
    property_type: str  # House, Flat, Plot
    bedrooms: Optional[int] = 0
    bathrooms: Optional[int] = 0
    area_sqft: float
    location: str
    is_available: bool = True

class Agent(BaseModel):
    id: Optional[int] = None
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None

class Inquiry(BaseModel):
    message: Optional[str] = None
    status: str = "new"

class SupportTicket(BaseModel):
    customer_name: str
    phone: str
    issue_type: str  # e.g., Maintenance, Legal, Viewing Issue
    message: str
    priority: str = "0"  # 0: Low, 1: High
    property_id: Optional[int] = None

# ===========================================================================
# --- Core Helpers ---
# ===========================================================================

def get_odoo_models(user=None, password=None):
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        login = user or ODOO_USER
        pwd = password or ODOO_PASSWORD
        uid = common.authenticate(ODOO_DB, login, pwd, {})
        if not uid: return None, None
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        return uid, models
    except Exception as e:
        logger.error(f"Odoo Connection Error: {e}")
        return None, None

def create_tokens(subject: str, payload: dict = {}):
    access_delta = datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_delta = datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    data = {"sub": subject, **payload}
    access_token = jwt.encode({**data, "exp": datetime.datetime.utcnow() + access_delta}, JWT_SECRET, algorithm=ALGORITHM)
    refresh_token = jwt.encode({**data, "refresh": True, "exp": datetime.datetime.utcnow() + refresh_delta}, JWT_SECRET, algorithm=ALGORITHM)
    return access_token, refresh_token

def verify_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def fix_odoo_str(val):
    return val if isinstance(val, str) else None

def strip_html(text):
    if not text: return None
    return re.sub(r'<[^>]+>', '', str(text)).strip() or None

def get_current_user(auth: HTTPAuthorizationCredentials = Security(security)):
    return verify_token(auth.credentials)

def require_staff(user=Depends(get_current_user)):
    # Agent acts as staff for Real Estate
    if user.get("role") != "agent" and user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Agent/Staff access required")
    return user

def get_tag_id(models, uid, tag_name):
    tag_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'search', [[['name', '=', tag_name]]])
    if not tag_ids:
        return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'create', [{'name': tag_name}])
    return tag_ids[0]

# ===========================================================================
# --- Auth Endpoints ---
# ===========================================================================

@app.post("/token", response_model=Token, tags=["Auth"])
def login(req: LoginRequest):
    uid, models = get_odoo_models(req.username, req.password)
    if not uid: raise HTTPException(status_code=401, detail="Invalid Odoo credentials")
    user_data = models.execute_kw(ODOO_DB, uid, req.password, 'res.users', 'read', [uid], {'fields': ['name', 'login']})
    access, refresh = create_tokens(str(uid), {"name": user_data[0]['name'], "login": user_data[0]['login'], "role": "agent"})
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@app.post("/refresh", response_model=Token, tags=["Auth"])
def refresh_token(auth: HTTPAuthorizationCredentials = Security(security)):
    user = verify_token(auth.credentials)
    if not user.get("refresh"): raise HTTPException(status_code=401, detail="Not a refresh token")
    access, refresh = create_tokens(user["sub"], {k: v for k, v in user.items() if k not in ['exp', 'refresh']})
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

# ===========================================================================
# --- Property Endpoints (Using product.template) ---
# ===========================================================================

@app.get("/properties", response_model=List[Property], tags=["Properties"])
def list_properties(skip: int = 0, limit: int = 20):
    uid, models = get_odoo_models()
    categ_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'search', [[['name', '=', 'Real Estate']]])
    if not categ_ids: return []
    
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.template', 'search_read',
        [[['categ_id', 'in', categ_ids]]], 
        {'fields': ['id', 'name', 'list_price', 'description_sale', 'sale_ok'], 'offset': skip, 'limit': limit}
    )
    
    res = []
    for p in data:
        desc = fix_odoo_str(p.get('description_sale')) or ""
        # Mocking parsing bedrooms/bathrooms from description for this implementation
        res.append(Property(
            id=p['id'], name=p['name'], price=p['list_price'],
            property_type="House" if "House" in p['name'] else "Flat",
            bedrooms=3, bathrooms=2, area_sqft=1500, # Defaulting for now
            location="Pakistan", is_available=p['sale_ok']
        ))
    return res

@app.post("/properties", response_model=Property, tags=["Properties"])
def create_property(p: Property, user=Depends(require_staff)):
    uid, models = get_odoo_models()
    categ_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'search', [[['name', '=', 'Real Estate']]])
    if not categ_ids:
        categ_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'create', [{'name': 'Real Estate'}])
    else:
        categ_id = categ_ids[0]
        
    new_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.template', 'create', [{
        'name': p.name, 'list_price': p.price, 'categ_id': categ_id,
        'description_sale': f"Type: {p.property_type} | Bedrooms: {p.bedrooms} | Location: {p.location}",
        'type': 'service', 'sale_ok': True
    }])
    p.id = new_id
    return p

# ===========================================================================
# --- Inquiry Endpoints (Using crm.lead) ---
# ===========================================================================

@app.get("/inquiries", response_model=List[Inquiry], tags=["Inquiries"])
def list_inquiries(user=Depends(require_staff)):
    uid, models = get_odoo_models()
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'crm.lead', 'search_read',
        [[]], {'fields': ['id', 'contact_name', 'phone', 'description', 'stage_id']}
    )
    return [Inquiry(
        id=i['id'], customer_name=fix_odoo_str(i.get('contact_name')) or "Anonymous",
        customer_phone=fix_odoo_str(i.get('phone')) or "N/A",
        property_id=0, # Linked in description or custom field
        message=strip_html(i.get('description')),
        status=i.get('stage_id', [None, "new"])[1]
    ) for i in data]

@app.post("/inquiries", response_model=Inquiry, tags=["Inquiries"])
def create_inquiry(i: Inquiry):
    uid, models = get_odoo_models()
    new_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'crm.lead', 'create', [{
        'name': f"Inquiry for Property #{i.property_id}",
        'contact_name': i.customer_name,
        'phone': i.customer_phone,
        'description': i.message,
        'type': 'lead'
    }])
    i.id = new_id
    return i

# ===========================================================================
# --- Dashboard ---
# ===========================================================================

@app.get("/dashboard/stats", tags=["Dashboard"])
def get_stats(user=Depends(require_staff)):
    uid, models = get_odoo_models()
    categ_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'search', [[['name', '=', 'Real Estate']]])
    return {
        "total_properties": models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.template', 'search_count', [[['categ_id', 'in', categ_ids]]]) if categ_ids else 0,
        "active_inquiries": models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'crm.lead', 'search_count', [[['type', '=', 'lead']]]),
        "agents": models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_count', [[['category_id', 'in', [get_tag_id(models, uid, "Agent")]]]])
    }

@app.get("/", tags=["Root"])
def root():
    return {"message": "Welcome to Real Estate & Property API", "docs": "/docs"}

# --- Customer Support Endpoints (Agent Escalation) ---

@app.post("/support/ticket", tags=["Customer Support"])
def create_support_ticket(ticket: SupportTicket):
    """Creates a support ticket in Odoo. Used by WhatsApp Agent for escalation."""
    uid, models = get_odoo_models()
    
    # 1. Ensure Support Project exists
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'Real Estate Support']]])
    if not project_ids:
        project_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'create', [{'name': 'Real Estate Support'}])
    else:
        project_id = project_ids[0]

    # 2. Create the ticket (Task)
    task_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'create', [{
        'name': f"[{ticket.issue_type}] {ticket.customer_name}",
        'project_id': project_id,
        'description': f"Phone: {ticket.phone}\nIssue: {ticket.message}\nProperty ID: {ticket.property_id or 'N/A'}",
        'priority': ticket.priority
    }])
    
    return {"status": "ticket_created", "ticket_id": task_id, "message": "An agent will contact you shortly regarding your request."}

@app.get("/support/my-tickets", tags=["Customer Support"])
def list_my_tickets(phone: str):
    """Fetch status of all real estate support tickets associated with a phone number"""
    uid, models = get_odoo_models()
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'Real Estate Support']]])
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
