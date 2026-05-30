import os
import requests
import datetime
import logging
import re
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="School Management API", version="1.0.0")

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

class Student(BaseModel):
    id: Optional[int] = None
    name: str
    student_id: str
    email: Optional[str] = None
    phone: Optional[str] = None

class Teacher(BaseModel):
    id: Optional[int] = None
    name: str
    employee_id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    department: str

class Course(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None

class Slide(BaseModel):
    id: Optional[int] = None
    name: str
    slide_type: str
    url: Optional[str] = None

class SupportTicket(BaseModel):
    customer_name: str
    phone: str
    issue_type: str
    message: str
    priority: str = "0"
    related_id: Optional[int] = None

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
# --- Student Endpoints ---
# ===========================================================================

@app.get("/students", response_model=List[Student], tags=["Students"])
def list_students(session_id: str = Depends(get_current_session)):
    tag_id = get_tag_id("Student", session_id)
    data = odoo_call_kw('res.partner', 'search_read', [[['category_id', 'in', [tag_id]]]], {'fields': ['id', 'name', 'ref', 'email', 'phone']}, session_id)
    return [Student(
        id=s['id'], name=s['name'], student_id=s.get('ref') or "N/A",
        email=s.get('email'), phone=s.get('phone')
    ) for s in data]

@app.post("/students", response_model=Student, tags=["Students"])
def create_student(s: Student, session_id: str = Depends(get_current_session)):
    tag_id = get_tag_id("Student", session_id)
    new_id = odoo_call_kw('res.partner', 'create', [{
        'name': s.name, 'ref': s.student_id, 'email': s.email, 'phone': s.phone,
        'category_id': [(4, tag_id)]
    }], {}, session_id)
    s.id = new_id
    return s

# ===========================================================================
# --- Teacher Endpoints ---
# ===========================================================================

@app.get("/teachers", response_model=List[Teacher], tags=["Teachers"])
def list_teachers(session_id: str = Depends(get_current_session)):
    tag_id = get_tag_id("Teacher", session_id)
    data = odoo_call_kw('res.partner', 'search_read', [[['category_id', 'in', [tag_id]]]], {'fields': ['id', 'name', 'ref', 'email', 'phone', 'function']}, session_id)
    return [Teacher(
        id=t['id'], name=t['name'], employee_id=t.get('ref') or "N/A",
        email=t.get('email'), phone=t.get('phone'), department=t.get('function') or "General"
    ) for t in data]

@app.post("/teachers", response_model=Teacher, tags=["Teachers"])
def create_teacher(t: Teacher, session_id: str = Depends(get_current_session)):
    tag_id = get_tag_id("Teacher", session_id)
    new_id = odoo_call_kw('res.partner', 'create', [{
        'name': t.name, 'ref': t.employee_id, 'email': t.email, 'phone': t.phone,
        'function': t.department, 'category_id': [(4, tag_id)]
    }], {}, session_id)
    t.id = new_id
    return t

# ===========================================================================
# --- LMS / Courses Endpoints ---
# ===========================================================================

@app.get("/lms/courses", response_model=List[Course], tags=["LMS - Courses"])
def list_courses(session_id: str = Depends(get_current_session)):
    data = odoo_call_kw('slide.channel', 'search_read', [[]], {'fields': ['id', 'name', 'description']}, session_id)
    return [Course(
        id=c['id'], name=c['name'], description=strip_html(c.get('description'))
    ) for c in data]

@app.get("/lms/courses/{course_id}/slides", response_model=List[Slide], tags=["LMS - Courses"])
def list_slides(course_id: int, session_id: str = Depends(get_current_session)):
    data = odoo_call_kw('slide.slide', 'search_read', [[['channel_id', '=', course_id]]], {'fields': ['id', 'name', 'slide_type', 'url']}, session_id)
    return [Slide(
        id=s['id'], name=s['name'], slide_type=s['slide_type'], url=s.get('url')
    ) for s in data]

# ===========================================================================
# --- Dashboard ---
# ===========================================================================

@app.get("/dashboard/stats", tags=["Dashboard"])
def get_stats(session_id: str = Depends(get_current_session)):
    s_tag = get_tag_id("Student", session_id)
    t_tag = get_tag_id("Teacher", session_id)
    return {
        "students": odoo_call_kw('res.partner', 'search_count', [[['category_id', 'in', [s_tag]]]], {}, session_id),
        "teachers": odoo_call_kw('res.partner', 'search_count', [[['category_id', 'in', [t_tag]]]], {}, session_id),
        "courses": odoo_call_kw('slide.channel', 'search_count', [[]], {}, session_id)
    }

@app.get("/", tags=["Root"])
def root():
    return {"message": "Welcome to School Management API", "docs": "/docs"}

# --- Customer Support Endpoints (Agent Escalation) ---

@app.post("/support/ticket", tags=["Customer Support"])
def create_support_ticket(ticket: SupportTicket, session_id: str = Depends(get_current_session)):
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'School Support']]], {}, session_id)
    if not project_ids:
        project_id = odoo_call_kw('project.project', 'create', [{'name': 'School Support'}], {}, session_id)
    else:
        project_id = project_ids[0]

    task_id = odoo_call_kw('project.task', 'create', [{
        'name': f"[{ticket.issue_type}] {ticket.customer_name}",
        'project_id': project_id,
        'description': f"Phone: {ticket.phone}\nIssue: {ticket.message}\nRelated ID: {ticket.related_id or 'N/A'}",
        'priority': ticket.priority
    }], {}, session_id)
    return {"status": "ticket_created", "ticket_id": task_id, "message": "Administration has been notified."}

@app.get("/support/my-tickets", tags=["Customer Support"])
def list_my_tickets(phone: str, session_id: str = Depends(get_current_session)):
    project_ids = odoo_call_kw('project.project', 'search', [[['name', '=', 'School Support']]], {}, session_id)
    if not project_ids: return []
    tasks = odoo_call_kw('project.task', 'search_read', [[['project_id', '=', project_ids[0]], ['description', 'ilike', phone]]], {'fields': ['id', 'name', 'stage_id', 'create_date']}, session_id)
    return [{"ticket_id": t['id'], "subject": t['name'], "status": t['stage_id'][1] if t.get('stage_id') else "New", "created_at": t['create_date']} for t in tasks]
