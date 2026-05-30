import os
import xmlrpc.client
import jwt
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
# --- Core Helpers ---
# ===========================================================================

def get_odoo_models(user=None, password=None):
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        login = user or ODOO_USER
        pwd = password or ODOO_PASSWORD
        uid = common.authenticate(ODOO_DB, login, pwd, {})
        if not uid:
            return None, None
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

import re
def strip_html(text):
    """Remove HTML tags returned by Odoo rich-text fields"""
    if not text:
        return None
    return re.sub(r'<[^>]+>', '', str(text)).strip() or None

def get_current_user(auth: HTTPAuthorizationCredentials = Security(security)):
    return verify_token(auth.credentials)

def require_staff(user=Depends(get_current_user)):
    if user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Staff access required")
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
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid Odoo credentials")
    user_data = models.execute_kw(ODOO_DB, uid, req.password, 'res.users', 'read', [uid], {'fields': ['name', 'login']})
    access, refresh = create_tokens(str(uid), {"name": user_data[0]['name'], "login": user_data[0]['login'], "role": "staff"})
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@app.post("/refresh", response_model=Token, tags=["Auth"])
def refresh_token(auth: HTTPAuthorizationCredentials = Security(security)):
    user = verify_token(auth.credentials)
    if not user.get("refresh"):
        raise HTTPException(status_code=401, detail="Not a refresh token")
    access, refresh = create_tokens(user["sub"], {k: v for k, v in user.items() if k not in ['exp', 'refresh']})
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

# ===========================================================================
# --- Patient Endpoints ---
# ===========================================================================

@app.get("/patients", response_model=List[Patient], tags=["Patients"])
def list_patients(skip: int = 0, limit: int = 20, user=Depends(require_staff)):
    uid, models = get_odoo_models()
    tag_id = get_tag_id(models, uid, "Patient")
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_read',
        [[['category_id', 'in', [tag_id]]]],
        {'fields': ['id', 'name', 'ref', 'email', 'phone', 'comment'], 'offset': skip, 'limit': limit}
    )
    return [Patient(
        id=p['id'], name=p['name'], patient_id=fix_odoo_str(p.get('ref')) or "N/A",
        email=fix_odoo_str(p.get('email')), phone=fix_odoo_str(p.get('phone')),
        blood_group=fix_odoo_str(p.get('comment'))
    ) for p in data]

@app.post("/patients", response_model=Patient, tags=["Patients"])
def create_patient(p: Patient, user=Depends(require_staff)):
    uid, models = get_odoo_models()
    tag_id = get_tag_id(models, uid, "Patient")
    new_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
        'name': p.name, 'ref': p.patient_id, 'email': p.email, 'phone': p.phone,
        'comment': p.blood_group, 'category_id': [(4, tag_id)]
    }])
    p.id = new_id
    return p

# ===========================================================================
# --- Doctor Endpoints ---
# ===========================================================================

@app.get("/doctors", response_model=List[Doctor], tags=["Doctors"])
def list_doctors(user=Depends(get_current_user)):
    uid, models = get_odoo_models()
    tag_id = get_tag_id(models, uid, "Doctor")
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_read',
        [[['category_id', 'in', [tag_id]]]],
        {'fields': ['id', 'name', 'function', 'email', 'phone']}
    )
    return [Doctor(
        id=d['id'], name=d['name'], specialty=fix_odoo_str(d.get('function')) or "General Physician",
        email=fix_odoo_str(d.get('email')), phone=fix_odoo_str(d.get('phone'))
    ) for d in data]

# ===========================================================================
# --- Appointment Endpoints ---
# ===========================================================================

@app.get("/appointments", response_model=List[Appointment], tags=["Appointments"])
def list_appointments(user=Depends(get_current_user)):
    uid, models = get_odoo_models()
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'calendar.event', 'search_read',
        [[]], {'fields': ['id', 'name', 'start', 'stop', 'partner_ids']}
    )
    res = []
    for a in data:
        p_ids = a.get('partner_ids', [])
        if len(p_ids) >= 2:
            res.append(Appointment(
                id=a['id'], name=a['name'], start=a['start'], stop=a['stop'],
                patient_id=p_ids[0], doctor_id=p_ids[1]
            ))
    return res

@app.post("/appointments", response_model=Appointment, tags=["Appointments"])
def create_appointment(a: Appointment, user=Depends(get_current_user)):
    uid, models = get_odoo_models()
    new_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'calendar.event', 'create', [{
        'name': a.name, 'start': a.start.strftime('%Y-%m-%d %H:%M:%S'),
        'stop': a.stop.strftime('%Y-%m-%d %H:%M:%S'),
        'partner_ids': [(6, 0, [a.patient_id, a.doctor_id])]
    }])
    a.id = new_id
    return a

# ===========================================================================
# --- Department Endpoints (Using project.project) ---
# ===========================================================================

@app.get("/departments", response_model=List[Department], tags=["Departments"])
def list_departments(user=Depends(get_current_user)):
    uid, models = get_odoo_models()
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search_read',
        [[]], {'fields': ['id', 'name']}
    )
    return [Department(id=d['id'], name=d['name']) for d in data]

# ===========================================================================
# --- Lab Report Endpoints (Using project.task) ---
# ===========================================================================

@app.get("/lab-reports", response_model=List[LabReport], tags=["Lab Reports"])
def list_lab_reports(user=Depends(get_current_user)):
    uid, models = get_odoo_models()
    # Find project named "Lab Reports"
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'Lab Reports']]])
    if not project_ids: return []
    
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'search_read',
        [[['project_id', '=', project_ids[0]]]], {'fields': ['id', 'partner_id', 'user_ids', 'name', 'description', 'stage_id']}
    )
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
def list_opd(user=Depends(get_current_user)):
    uid, models = get_odoo_models()
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'OPD']]])
    if not project_ids: return []
    
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'search_read',
        [[['project_id', '=', project_ids[0]]]], {'fields': ['id', 'partner_id', 'user_ids', 'project_id', 'name', 'description']}
    )
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
def list_operations(user=Depends(get_current_user)):
    uid, models = get_odoo_models()
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'Operations']]])
    if not project_ids: return []
    
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'search_read',
        [[['project_id', '=', project_ids[0]]]], {'fields': ['id', 'partner_id', 'user_ids', 'project_id', 'name', 'date_deadline', 'stage_id']}
    )
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
def get_stats(user=Depends(require_staff)):
    uid, models = get_odoo_models()
    p_tag = get_tag_id(models, uid, "Patient")
    d_tag = get_tag_id(models, uid, "Doctor")
    return {
        "patients": models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_count', [[['category_id', 'in', [p_tag]]]]),
        "doctors": models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_count', [[['category_id', 'in', [d_tag]]]]),
        "appointments": models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'calendar.event', 'search_count', [[]])
    }

@app.get("/", tags=["Root"])
def root():
    return {"message": "Welcome to Hospital Management API", "docs": "/docs"}

# --- Customer Support Endpoints (Agent Escalation) ---

@app.post("/support/ticket", tags=["Customer Support"])
def create_support_ticket(ticket: SupportTicket):
    """Creates a support ticket in Odoo. Used by WhatsApp Agent for escalation."""
    uid, models = get_odoo_models()
    
    # 1. Ensure Support Project exists
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'Hospital Support']]])
    if not project_ids:
        project_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'create', [{'name': 'Hospital Support'}])
    else:
        project_id = project_ids[0]

    # 2. Create the ticket (Task)
    task_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'create', [{
        'name': f"[{ticket.issue_type}] {ticket.customer_name}",
        'project_id': project_id,
        'description': f"Phone: {ticket.phone}\nIssue: {ticket.message}\nRelated ID: {ticket.related_id or 'N/A'}",
        'priority': ticket.priority
    }])
    
    return {"status": "ticket_created", "ticket_id": task_id, "message": "Medical staff has been notified for follow-up."}

@app.get("/support/my-tickets", tags=["Customer Support"])
def list_my_tickets(phone: str):
    """Fetch status of all hospital support tickets associated with a phone number"""
    uid, models = get_odoo_models()
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'Hospital Support']]])
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
