import os
import requests
import datetime
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, Security, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Hospital Management API", version="1.0.0", description="Odoo-Integrated Hospital Management API")

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

# ===========================================================================
# --- Pydantic Models ---
# ===========================================================================

class Token(BaseModel):
    session_id: str
    token_type: str

class LoginRequest(BaseModel):
    username: str
    password: str

class Patient(BaseModel):
    id: Optional[int] = None
    name: str
    patient_id: str  # maps to Odoo ref
    email: Optional[str] = None
    phone: Optional[str] = None
    blood_group: Optional[str] = None

class Doctor(BaseModel):
    id: Optional[int] = None
    name: str
    specialty: str  # maps to Odoo function
    email: Optional[str] = None
    phone: Optional[str] = None

class Appointment(BaseModel):
    id: Optional[int] = None
    patient_id: int
    doctor_id: int
    start: datetime.datetime
    stop: datetime.datetime
    name: str  # Purpose of visit
    status: Optional[str] = "draft"

class LabReport(BaseModel):
    id: Optional[int] = None
    patient_id: int
    doctor_id: int
    test_type: str
    result: Optional[str] = None
    status: str = "pending"

class OPDRecord(BaseModel):
    id: Optional[int] = None
    patient_id: int
    doctor_id: int
    department_id: int
    symptoms: str
    diagnosis: Optional[str] = None
    status: str = "New"

class Operation(BaseModel):
    id: Optional[int] = None
    patient_id: int
    doctor_id: int
    department_id: int
    operation_name: str
    date: datetime.datetime
    status: str = "scheduled"

class Department(BaseModel):
    id: int
    name: str

class SupportTicket(BaseModel):
    customer_name: str
    phone: str
    issue_type: str  # e.g., Medical Inquiry, Billing, Urgent
    message: str
    priority: str = "0"  # 0: Low, 1: High
    related_id: Optional[int] = None # Patient or Appointment ID

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

def fix_odoo_str(val):
    return val if isinstance(val, str) else None

import re
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
# --- Patient Endpoints ---
# ===========================================================================

@app.get("/patients", response_model=List[Patient], tags=["Patients"])
def list_patients(skip: int = 0, limit: int = 20, session_id: str = Depends(get_current_session)):
    tag_id = get_tag_id("Patient", session_id)
    data = odoo_call_kw('res.partner', 'search_read', [[['category_id', 'in', [tag_id]]]], {'fields': ['id', 'name', 'ref', 'email', 'phone', 'comment'], 'offset': skip, 'limit': limit}, session_id)
    return [Patient(
        id=p['id'], name=p['name'], patient_id=fix_odoo_str(p.get('ref')) or "N/A",
        email=fix_odoo_str(p.get('email')), phone=fix_odoo_str(p.get('phone')),
        blood_group=fix_odoo_str(p.get('comment'))
    ) for p in data]

@app.post("/patients", response_model=Patient, tags=["Patients"])
def create_patient(p: Patient, session_id: str = Depends(get_current_session)):
    tag_id = get_tag_id("Patient", session_id)
    new_id = odoo_call_kw('res.partner', 'create', [{
        'name': p.name, 'ref': p.patient_id, 'email': p.email, 'phone': p.phone,
        'comment': p.blood_group, 'category_id': [(4, tag_id)]
    }], {}, session_id)
    p.id = new_id
    return p

# ===========================================================================
# --- Doctor Endpoints ---
# ===========================================================================

@app.get("/doctors", response_model=List[Doctor], tags=["Doctors"])
def list_doctors(session_id: str = Depends(get_current_session)):
    tag_id = get_tag_id("Doctor", session_id)
    data = odoo_call_kw('res.partner', 'search_read', [[['category_id', 'in', [tag_id]]]], {'fields': ['id', 'name', 'function', 'email', 'phone']}, session_id)
    return [Doctor(
        id=d['id'], name=d['name'], specialty=fix_odoo_str(d.get('function')) or "General Physician",
        email=fix_odoo_str(d.get('email')), phone=fix_odoo_str(d.get('phone'))
    ) for d in data]

# ===========================================================================
# --- Appointment Endpoints ---
# ===========================================================================

@app.get("/appointments", response_model=List[Appointment], tags=["Appointments"])
def list_appointments(session_id: str = Depends(get_current_session)):
    data = odoo_call_kw('calendar.event', 'search_read', [[]], {'fields': ['id', 'name', 'start', 'stop', 'partner_ids']}, session_id)
    res = []
    for a in data:
        p_ids = a.get('partner_ids', [])
        if len(p_ids) >= 2:
            res.append(Appointment(id=a['id'], name=a['name'], start=a['start'], stop=a['stop'], patient_id=p_ids[0], doctor_id=p_ids[1]))
    return res

@app.post("/appointments", response_model=Appointment, tags=["Appointments"])
def create_appointment(a: Appointment, session_id: str = Depends(get_current_session)):
    new_id = odoo_call_kw('calendar.event', 'create', [{
        'name': a.name, 'start': a.start.strftime('%Y-%m-%d %H:%M:%S'),
        'stop': a.stop.strftime('%Y-%m-%d %H:%M:%S'),
        'partner_ids': [(6, 0, [a.patient_id, a.doctor_id])]
    }], {}, session_id)
    a.id = new_id
    return a

# ===========================================================================
# --- Department Endpoints (Using project.project) ---
# ===========================================================================

@app.get("/departments", response_model=List[Department], tags=["Departments"])
def list_departments(session_id: str = Depends(get_current_session)):
    data = odoo_call_kw('project.project', 'search_read', [[]], {'fields': ['id', 'name']}, session_id)
    return [Department(id=d['id'], name=d['name']) for d in data]

# ===========================================================================
# --- Lab Report Endpoints (Using project.task) ---
# ===========================================================================

@app.get("/lab-reports", response_model=List[LabReport], tags=["Lab Reports"])
def list_lab_reports(session_id: str = Depends(get_current_session)):
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'Lab Reports']]], {}, session_id)
    if not project_ids: return []
    data = odoo_call_kw('project.task', 'search_read', [[['project_id', '=', project_ids[0]]]], {'fields': ['id', 'partner_id', 'user_ids', 'name', 'description', 'stage_id']}, session_id)
    return [LabReport(
        id=r['id'], patient_id=r['partner_id'][0] if r.get('partner_id') else 0,
        doctor_id=r['user_ids'][0] if r.get('user_ids') else 0,
        test_type=r['name'], result=strip_html(r.get('description')),
        status="completed" if r.get('stage_id') and "Done" in r['stage_id'][1] else "pending"
    ) for r in data]

# ===========================================================================
# --- OPD Endpoints (Using project.task) ---
# ===========================================================================

@app.get("/opd", response_model=List[OPDRecord], tags=["OPD"])
def list_opd(session_id: str = Depends(get_current_session)):
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'OPD']]], {}, session_id)
    if not project_ids: return []
    data = odoo_call_kw('project.task', 'search_read', [[['project_id', '=', project_ids[0]]]], {'fields': ['id', 'partner_id', 'user_ids', 'project_id', 'name', 'description']}, session_id)
    return [OPDRecord(
        id=r['id'], patient_id=r['partner_id'][0] if r.get('partner_id') else 0,
        doctor_id=r['user_ids'][0] if r.get('user_ids') else 0,
        department_id=r['project_id'][0], symptoms=r['name'],
        diagnosis=strip_html(r.get('description')),
        status=r['stage_id'][1] if r.get('stage_id') else "New"
    ) for r in data]

# ===========================================================================
# --- Operation Endpoints (Using project.task) ---
# ===========================================================================

@app.get("/operations", response_model=List[Operation], tags=["Operations"])
def list_operations(session_id: str = Depends(get_current_session)):
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'Operations']]], {}, session_id)
    if not project_ids: return []
    data = odoo_call_kw('project.task', 'search_read', [[['project_id', '=', project_ids[0]]]], {'fields': ['id', 'partner_id', 'user_ids', 'project_id', 'name', 'date_deadline', 'stage_id']}, session_id)
    return [Operation(
        id=r['id'], patient_id=r['partner_id'][0] if r.get('partner_id') else 0,
        doctor_id=r['user_ids'][0] if r.get('user_ids') else 0,
        department_id=r['project_id'][0], operation_name=r['name'],
        date=r.get('date_deadline') or datetime.datetime.now(),
        status="completed" if r.get('stage_id') and "Done" in r['stage_id'][1] else "scheduled"
    ) for r in data]

# ===========================================================================
# --- Dashboard ---
# ===========================================================================

@app.get("/dashboard/stats", tags=["Dashboard"])
def get_stats(session_id: str = Depends(get_current_session)):
    p_tag = get_tag_id("Patient", session_id)
    d_tag = get_tag_id("Doctor", session_id)
    return {
        "patients": odoo_call_kw('res.partner', 'search_count', [[['category_id', 'in', [p_tag]]]], {}, session_id),
        "doctors": odoo_call_kw('res.partner', 'search_count', [[['category_id', 'in', [d_tag]]]], {}, session_id),
        "appointments": odoo_call_kw('calendar.event', 'search_count', [[]], {}, session_id)
    }

@app.get("/", tags=["Root"])
def root():
    return {"message": "Welcome to Hospital Management API", "docs": "/docs"}

# --- Customer Support Endpoints (Agent Escalation) ---

@app.post("/support/ticket", tags=["Customer Support"])
def create_support_ticket(ticket: SupportTicket, session_id: str = Depends(get_current_session)):
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'Hospital Support']]], {}, session_id)
    if not project_ids:
        project_id = odoo_call_kw('project.project', 'create', [{'name': 'Hospital Support'}], {}, session_id)
    else:
        project_id = project_ids[0]

    task_id = odoo_call_kw('project.task', 'create', [{
        'name': f"[{ticket.issue_type}] {ticket.customer_name}",
        'project_id': project_id,
        'description': f"Phone: {ticket.phone}\nIssue: {ticket.message}\nRelated ID: {ticket.related_id or 'N/A'}",
        'priority': ticket.priority
    }], {}, session_id)
    return {"status": "ticket_created", "ticket_id": task_id, "message": "Medical staff has been notified."}

@app.get("/support/my-tickets", tags=["Customer Support"])
def list_my_tickets(phone: str, session_id: str = Depends(get_current_session)):
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'Hospital Support']]], {}, session_id)
    if not project_ids: return []
    tasks = odoo_call_kw('project.task', 'search_read', [[['project_id', '=', project_ids[0]], ['description', 'ilike', phone]]], {'fields': ['id', 'name', 'stage_id', 'create_date']}, session_id)
    return [{"ticket_id": t['id'], "subject": t['name'], "status": t['stage_id'][1] if t.get('stage_id') else "New", "created_at": t['create_date']} for t in tasks]
