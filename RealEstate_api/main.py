import os
import requests
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()

app = FastAPI(title="Real Estate CRM API", version="1.0.0")

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

# ===========================================================================
# --- Pydantic Models ---
# ===========================================================================

class Token(BaseModel):
    session_id: str
    token_type: str

class LoginRequest(BaseModel):
    username: str
    password: str

class Property(BaseModel):
    id: Optional[int] = None
    name: str  # e.g., "3 BHK Apartment in Downtown"
    price: float
    description: Optional[str] = None
    status: str = "available"  # available, sold, rented
    agent_id: Optional[int] = None

class Inquiry(BaseModel):
    id: Optional[int] = None
    customer_name: str
    phone: str
    email: Optional[str] = None
    property_id: Optional[int] = None
    message: str
    status: str = "new"

class SupportTicket(BaseModel):
    customer_name: str
    phone: str
    issue_type: str  # e.g., Maintenance, Contract, Payment
    message: str
    priority: str = "0"
    related_property_id: Optional[int] = None

# ===========================================================================
# --- Core Native Auth Helpers ---
# ===========================================================================

def get_current_session(auth: HTTPAuthorizationCredentials = Security(security)):
    return auth.credentials

def odoo_call_kw(model, method, args=[], kwargs={}, session_id=None):
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
        raise HTTPException(status_code=500, detail="Internal Server Error")

def strip_html(text):
    if not text: return None
    return re.sub(r'<[^>]+>', '', str(text)).strip() or None

def get_tag_id(tag_name, session_id):
    tag_ids = odoo_call_kw('res.partner.category', 'search', [[['name', '=', tag_name]]], {}, session_id)
    if not tag_ids:
        return odoo_call_kw('res.partner.category', 'create', [{'name': tag_name}], {}, session_id)
    return tag_ids[0]

# ===========================================================================
# --- Auth Endpoints ---
# ===========================================================================

@app.post("/login", response_model=Token, tags=["Auth"])
def login(req: LoginRequest):
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
    if not session_id: raise HTTPException(status_code=500, detail="Odoo did not return a session_id")
    return {"session_id": session_id, "token_type": "bearer"}

# ===========================================================================
# --- Property Catalog (Products) ---
# ===========================================================================

@app.get("/properties", response_model=List[Property], tags=["Properties"])
def list_properties(session_id: str = Depends(get_current_session)):
    categ_ids = odoo_call_kw('product.category', 'search', [[['name', '=', 'Real Estate']]], {}, session_id)
    if not categ_ids: return []
    data = odoo_call_kw('product.product', 'search_read', [[['categ_id', '=', categ_ids[0]]]], {'fields': ['id', 'name', 'list_price', 'description_sale']}, session_id)
    return [Property(
        id=p['id'], name=p['name'], price=p['list_price'],
        description=strip_html(p.get('description_sale')), status="available"
    ) for p in data]

@app.post("/properties", response_model=Property, tags=["Properties"])
def create_property(p: Property, session_id: str = Depends(get_current_session)):
    categ_ids = odoo_call_kw('product.category', 'search', [[['name', '=', 'Real Estate']]], {}, session_id)
    if not categ_ids:
        categ_id = odoo_call_kw('product.category', 'create', [{'name': 'Real Estate'}], {}, session_id)
    else:
        categ_id = categ_ids[0]

    new_id = odoo_call_kw('product.product', 'create', [{
        'name': p.name, 'list_price': p.price, 'description_sale': p.description,
        'type': 'service', 'categ_id': categ_id
    }], {}, session_id)
    p.id = new_id
    return p

# ===========================================================================
# --- Inquiries (CRM Leads) ---
# ===========================================================================

@app.post("/inquiries", response_model=Inquiry, tags=["Inquiries"])
def submit_inquiry(inq: Inquiry, session_id: str = Depends(get_current_session)):
    new_id = odoo_call_kw('crm.lead', 'create', [{
        'name': f"Inquiry for Property {inq.property_id or 'General'}",
        'contact_name': inq.customer_name, 'phone': inq.phone,
        'email_from': inq.email, 'description': inq.message, 'type': 'lead'
    }], {}, session_id)
    inq.id = new_id
    return inq

@app.get("/inquiries", response_model=List[Inquiry], tags=["Inquiries"])
def list_inquiries(session_id: str = Depends(get_current_session)):
    data = odoo_call_kw('crm.lead', 'search_read', [[]], {'fields': ['id', 'contact_name', 'phone', 'description', 'stage_id']}, session_id)
    return [Inquiry(
        id=l['id'], customer_name=l.get('contact_name') or "Unknown",
        phone=l.get('phone') or "", message=strip_html(l.get('description')) or "",
        status=l['stage_id'][1] if l.get('stage_id') else "new"
    ) for l in data]

# ===========================================================================
# --- Dashboard ---
# ===========================================================================

@app.get("/dashboard/stats", tags=["Dashboard"])
def get_stats(session_id: str = Depends(get_current_session)):
    categ_ids = odoo_call_kw('product.category', 'search', [[['name', '=', 'Real Estate']]], {}, session_id)
    return {
        "total_properties": odoo_call_kw('product.product', 'search_count', [[['categ_id', '=', categ_ids[0]]]] if categ_ids else [[]], {}, session_id),
        "total_inquiries": odoo_call_kw('crm.lead', 'search_count', [[]], {}, session_id),
        "won_deals": odoo_call_kw('crm.lead', 'search_count', [[['stage_id.name', 'ilike', 'Won']]], {}, session_id)
    }

@app.get("/", tags=["Root"])
def root():
    return {"message": "Welcome to Real Estate API", "docs": "/docs"}

# --- Customer Support Endpoints (Agent Escalation) ---

@app.post("/support/ticket", tags=["Customer Support"])
def create_support_ticket(ticket: SupportTicket, session_id: str = Depends(get_current_session)):
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'Real Estate Support']]], {}, session_id)
    if not project_ids:
        project_id = odoo_call_kw('project.project', 'create', [{'name': 'Real Estate Support'}], {}, session_id)
    else:
        project_id = project_ids[0]

    task_id = odoo_call_kw('project.task', 'create', [{
        'name': f"[{ticket.issue_type}] {ticket.customer_name}",
        'project_id': project_id,
        'description': f"Phone: {ticket.phone}\nIssue: {ticket.message}\nRelated Property ID: {ticket.related_property_id or 'N/A'}",
        'priority': ticket.priority
    }], {}, session_id)
    return {"status": "ticket_created", "ticket_id": task_id, "message": "An agent will contact you shortly."}

@app.get("/support/my-tickets", tags=["Customer Support"])
def list_my_tickets(phone: str, session_id: str = Depends(get_current_session)):
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'Real Estate Support']]], {}, session_id)
    if not project_ids: return []
    tasks = odoo_call_kw('project.task', 'search_read', [[['project_id', '=', project_ids[0]], ['description', 'ilike', phone]]], {'fields': ['id', 'name', 'stage_id', 'create_date']}, session_id)
    return [{"ticket_id": t['id'], "subject": t['name'], "status": t['stage_id'][1] if t.get('stage_id') else "New", "created_at": t['create_date']} for t in tasks]
