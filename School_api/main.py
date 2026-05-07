import os
import xmlrpc.client
import jwt
import datetime
from fastapi import FastAPI, HTTPException, Depends, Security, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="School Management API", version="2.0.0", description="100% Odoo-Integrated School & LMS API")

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

class StudentLoginRequest(BaseModel):
    student_id: str
    email: str

class Student(BaseModel):
    id: Optional[int] = None
    name: str
    student_id: str
    email: Optional[str] = None
    phone: Optional[str] = None

class StudentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class Teacher(BaseModel):
    id: Optional[int] = None
    name: str
    subject: str
    email: Optional[str] = None

class Course(BaseModel):
    id: int
    name: str
    price: float

class LMSCourse(BaseModel):
    id: int
    name: str
    total_slides: int
    is_published: bool

class LMSCourseDetail(BaseModel):
    id: int
    name: str
    total_slides: int
    is_published: bool
    description: Optional[str] = None
    members_count: Optional[int] = None

class LMSSlide(BaseModel):
    id: int
    name: str
    slide_type: str
    is_preview: bool

class LMSSlideDetail(BaseModel):
    id: int
    name: str
    slide_type: str
    is_preview: bool
    description: Optional[str] = None

class LMSMember(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    completion: float = 0.0

class LMSReportRow(BaseModel):
    student_id: int
    student_name: str
    course_id: int
    course_name: str
    completion: float
    last_action: Optional[str] = None

class LMSProgress(BaseModel):
    channel_id: int
    channel_name: str
    completion: float
    slides_completed: int
    total_slides: int

class QuizQuestion(BaseModel):
    id: int
    question: str
    answers: List[dict]

class QuizSubmission(BaseModel):
    answers: List[dict]  # [{"question_id": 1, "answer_id": 2}]

class SupportTicket(BaseModel):
    customer_name: str
    phone: str
    issue_type: str  # e.g., Technical, Fees, Admissions
    message: str
    priority: str = "0"  # 0: Low, 1: High
    related_id: Optional[int] = None # Student or Course ID

# ===========================================================================
# --- Core Helpers ---
# ===========================================================================

def get_odoo_models(user=None, password=None):
    """Connects to Odoo. Uses provided credentials or system defaults."""
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
    """Odoo XML-RPC returns False for empty strings. This converts it to None."""
    return val if isinstance(val, str) else None

def get_current_user(auth: HTTPAuthorizationCredentials = Security(security)):
    return verify_token(auth.credentials)

def require_staff(user=Depends(get_current_user)):
    if user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Staff access required")
    return user

def get_student_tag_id(models, uid):
    ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'search', [[['name', '=', 'Student']]])
    if not ids:
        return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'create', [{'name': 'Student'}])
    return ids[0]

def get_teacher_tag_id(models, uid):
    ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'search', [[['name', '=', 'Teacher']]])
    if not ids:
        return models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'create', [{'name': 'Teacher'}])
    return ids[0]

# ===========================================================================
# --- Authentication Endpoints ---
# ===========================================================================

@app.post("/token", response_model=Token, tags=["Auth"])
def login_staff(req: LoginRequest):
    """Authenticate staff against Odoo's real users (res.users)"""
    uid, models = get_odoo_models(req.username, req.password)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid Odoo credentials")
    user_data = models.execute_kw(ODOO_DB, uid, req.password, 'res.users', 'read', [uid], {'fields': ['name', 'login']})
    
    access, refresh = create_tokens(str(uid), {
        "name": user_data[0]['name'],
        "login": user_data[0]['login'],
        "role": "staff"
    })
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@app.post("/student/login", response_model=Token, tags=["Auth"])
def login_student(req: StudentLoginRequest):
    """Authenticate a student using their Student ID and Email from Odoo"""
    uid, models = get_odoo_models()
    tag_id = get_student_tag_id(models, uid)
    student = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_read',
        [[['ref', '=', req.student_id], ['email', '=', req.email], ['category_id', 'in', [tag_id]]]],
        {'limit': 1, 'fields': ['id', 'name', 'ref']}
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found or credentials mismatch")
    
    access, refresh = create_tokens(str(student[0]['id']), {
        "name": student[0]['name'],
        "student_id": student[0]['ref'],
        "role": "student"
    })
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@app.post("/refresh", response_model=Token, tags=["Auth"])
def refresh_token(auth: HTTPAuthorizationCredentials = Security(security)):
    """Exchanges a valid Refresh Token for a new set of tokens"""
    user = verify_token(auth.credentials)
    
    if not user.get("refresh"):
        raise HTTPException(status_code=401, detail="This is not a refresh token")
    
    # Generate new tokens
    access, refresh = create_tokens(user["sub"], {
        "name": user.get("name"),
        "login": user.get("login"),
        "student_id": user.get("student_id"),
        "role": user.get("role")
    })
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@app.get("/me", tags=["Auth"])
def get_me(user=Depends(get_current_user)):
    """Returns details of the currently logged-in user"""
    return user

# ===========================================================================
# --- Student Endpoints (res.partner) ---
# ===========================================================================

@app.get("/students", response_model=List[Student], tags=["Students"])
def list_students(
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(50, description="Max records to return"),
    user=Depends(get_current_user)
):
    """List all students from Odoo (paginated)"""
    uid, models = get_odoo_models()
    tag_id = get_student_tag_id(models, uid)
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_read',
        [[['category_id', 'in', [tag_id]]]],
        {'fields': ['id', 'name', 'ref', 'email', 'phone'], 'offset': skip, 'limit': limit}
    )
    return [Student(id=s['id'], name=s['name'], student_id=fix_odoo_str(s.get('ref')) or 'N/A', email=fix_odoo_str(s.get('email')), phone=fix_odoo_str(s.get('phone'))) for s in data]

@app.get("/students/{student_id}", response_model=Student, tags=["Students"])
def get_student(student_id: int, user=Depends(get_current_user)):
    """Get a single student's profile from Odoo"""
    uid, models = get_odoo_models()
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'read',
        [student_id], {'fields': ['id', 'name', 'ref', 'email', 'phone']}
    )
    if not data:
        raise HTTPException(status_code=404, detail="Student not found")
    s = data[0]
    return Student(id=s['id'], name=s['name'], student_id=fix_odoo_str(s.get('ref')) or 'N/A', email=fix_odoo_str(s.get('email')), phone=fix_odoo_str(s.get('phone')))

@app.post("/students", response_model=Student, tags=["Students"])
def create_student(student: Student, user=Depends(get_current_user)):
    """Create a new student in Odoo (Staff only)"""
    if user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Only staff can create students")
    uid, models = get_odoo_models()
    tag_id = get_student_tag_id(models, uid)
    new_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
        'name': student.name, 'ref': student.student_id,
        'email': student.email, 'phone': student.phone,
        'category_id': [(4, tag_id)]
    }])
    student.id = new_id
    return student

@app.put("/students/{student_id}", response_model=Student, tags=["Students"])
def update_student(student_id: int, update: StudentUpdate, user=Depends(get_current_user)):
    """Update a student's details in Odoo (Staff only)"""
    if user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Only staff can update student records")
    uid, models = get_odoo_models()
    vals = {k: v for k, v in update.dict().items() if v is not None}
    if not vals:
        raise HTTPException(status_code=400, detail="No fields to update")
    models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'write', [[student_id], vals])
    return get_student(student_id, user)

@app.delete("/students/{student_id}", tags=["Students"])
def delete_student(student_id: int, user=Depends(get_current_user)):
    """Archive (soft-delete) a student in Odoo (Staff only)"""
    if user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Only staff can delete students")
    uid, models = get_odoo_models()
    models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'write', [[student_id], {'active': False}])
    return {"status": "success", "message": f"Student {student_id} archived"}

# ===========================================================================
# --- Teacher Endpoints (res.partner) ---
# ===========================================================================

@app.get("/teachers", response_model=List[Teacher], tags=["Teachers"])
def list_teachers(user=Depends(get_current_user)):
    """List all teachers from Odoo"""
    uid, models = get_odoo_models()
    tag_id = get_teacher_tag_id(models, uid)
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_read',
        [[['category_id', 'in', [tag_id]]]],
        {'fields': ['id', 'name', 'function', 'email']}
    )
    return [Teacher(id=t['id'], name=t['name'], subject=fix_odoo_str(t.get('function')) or 'N/A', email=fix_odoo_str(t.get('email'))) for t in data]

@app.get("/teachers/{teacher_id}", response_model=Teacher, tags=["Teachers"])
def get_teacher(teacher_id: int, user=Depends(get_current_user)):
    """Get a single teacher's profile from Odoo"""
    uid, models = get_odoo_models()
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'read',
        [teacher_id], {'fields': ['id', 'name', 'function', 'email']}
    )
    if not data:
        raise HTTPException(status_code=404, detail="Teacher not found")
    t = data[0]
    return Teacher(id=t['id'], name=t['name'], subject=fix_odoo_str(t.get('function')) or 'N/A', email=fix_odoo_str(t.get('email')))

@app.post("/teachers", response_model=Teacher, tags=["Teachers"])
def create_teacher(teacher: Teacher, user=Depends(get_current_user)):
    """Create a new teacher in Odoo (Staff only)"""
    if user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Only staff can create teachers")
    uid, models = get_odoo_models()
    tag_id = get_teacher_tag_id(models, uid)
    new_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
        'name': teacher.name, 'function': teacher.subject,
        'email': teacher.email, 'category_id': [(4, tag_id)]
    }])
    teacher.id = new_id
    return teacher

@app.get("/teachers/{teacher_id}/courses", response_model=List[LMSCourse], tags=["Teachers"])
def get_teacher_courses(teacher_id: int, user=Depends(get_current_user)):
    """List LMS courses where this teacher is the responsible user"""
    uid, models = get_odoo_models()
    user_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.users', 'search', [[['partner_id', '=', teacher_id]]])
    if not user_ids:
        return []
    
    courses = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel', 'search_read',
        [[['user_id', '=', user_ids[0]]]], {'fields': ['id', 'name', 'total_slides', 'is_published']}
    )
    return [LMSCourse(id=c['id'], name=c['name'], total_slides=c['total_slides'], is_published=c['is_published']) for c in courses]

# ===========================================================================
# --- LMS / eLearning Endpoints (slide.channel, slide.slide) ---
# ===========================================================================

@app.get("/lms/courses", response_model=List[LMSCourse], tags=["LMS"])
def list_lms_courses(user=Depends(get_current_user)):
    """List all published eLearning courses from Odoo"""
    uid, models = get_odoo_models()
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel', 'search_read',
        [[]], {'fields': ['id', 'name', 'total_slides', 'is_published']}
    )
    return [LMSCourse(id=c['id'], name=c['name'], total_slides=c['total_slides'], is_published=c['is_published']) for c in data]

@app.get("/lms/courses/{channel_id}", response_model=LMSCourseDetail, tags=["LMS"])
def get_lms_course(channel_id: int, user=Depends(get_current_user)):
    """Get full details of a single LMS course"""
    uid, models = get_odoo_models()
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel', 'read',
        [channel_id], {'fields': ['id', 'name', 'total_slides', 'is_published', 'description', 'members_count']}
    )
    if not data:
        raise HTTPException(status_code=404, detail="LMS Course not found")
    c = data[0]
    return LMSCourseDetail(
        id=c['id'], name=c['name'], total_slides=c['total_slides'],
        is_published=c['is_published'], description=fix_odoo_str(c.get('description')) or '',
        members_count=c.get('members_count', 0)
    )

@app.get("/lms/courses/{channel_id}/content", response_model=List[LMSSlide], tags=["LMS"])
def get_lms_content(channel_id: int, user=Depends(get_current_user)):
    """List all lessons and slides for a specific LMS course"""
    uid, models = get_odoo_models()
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.slide', 'search_read',
        [[['channel_id', '=', channel_id]]], {'fields': ['id', 'name', 'slide_type', 'is_preview']}
    )
    return [LMSSlide(id=s['id'], name=s['name'], slide_type=s['slide_type'], is_preview=s['is_preview']) for s in data]

@app.get("/lms/courses/{channel_id}/content/{slide_id}", response_model=LMSSlideDetail, tags=["LMS"])
def get_lms_slide(channel_id: int, slide_id: int, user=Depends(get_current_user)):
    """Get details of a single lesson/slide"""
    uid, models = get_odoo_models()
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.slide', 'read',
        [slide_id], {'fields': ['id', 'name', 'slide_type', 'is_preview', 'description', 'channel_id']}
    )
    if not data or data[0].get('channel_id', [None])[0] != channel_id:
        raise HTTPException(status_code=404, detail="Slide not found in this course")
    s = data[0]
    return LMSSlideDetail(id=s['id'], name=s['name'], slide_type=s['slide_type'], is_preview=s['is_preview'], description=fix_odoo_str(s.get('description')) or '')

@app.post("/lms/courses/{channel_id}/enroll", tags=["LMS"])
def enroll_in_lms_course(channel_id: int, user=Depends(get_current_user)):
    """Enroll the currently logged-in student into an LMS course"""
    partner_id = int(user.get("sub"))
    uid, models = get_odoo_models()
    existing = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel.partner', 'search',
        [[['channel_id', '=', channel_id], ['partner_id', '=', partner_id]]]
    )
    if existing:
        return {"status": "already_enrolled", "message": "Already enrolled in this course"}
    enroll_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel.partner', 'create', [{
        'channel_id': channel_id, 'partner_id': partner_id,
    }])
    return {"status": "success", "enroll_id": enroll_id, "message": "Enrollment successful"}

@app.delete("/lms/courses/{channel_id}/unenroll", tags=["LMS"])
def unenroll_from_lms_course(channel_id: int, user=Depends(get_current_user)):
    """Unenroll the currently logged-in student from an LMS course"""
    partner_id = int(user.get("sub"))
    uid, models = get_odoo_models()
    existing = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel.partner', 'search',
        [[['channel_id', '=', channel_id], ['partner_id', '=', partner_id]]]
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel.partner', 'unlink', [existing])
    return {"status": "success", "message": "Unenrolled successfully"}

@app.get("/lms/courses/{channel_id}/members", response_model=List[LMSMember], tags=["LMS"])
def get_lms_members(channel_id: int, user=Depends(get_current_user)):
    """List all students enrolled in an LMS course with their completion progress (Staff only)"""
    if user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Staff access required")
    uid, models = get_odoo_models()
    enrollments = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel.partner', 'search_read',
        [[['channel_id', '=', channel_id]]], {'fields': ['partner_id', 'completion']}
    )
    if not enrollments:
        return []
    partner_ids = [e['partner_id'][0] for e in enrollments if e.get('partner_id')]
    partners = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'read',
        [partner_ids], {'fields': ['id', 'name', 'email']}
    )
    partner_map = {p['id']: p for p in partners}
    result = []
    for e in enrollments:
        p_id = e['partner_id'][0]
        if p_id in partner_map:
            result.append(LMSMember(
                id=p_id, 
                name=partner_map[p_id]['name'], 
                email=fix_odoo_str(partner_map[p_id].get('email')),
                completion=e.get('completion', 0.0)
            ))
    return result

@app.get("/lms/reporting", response_model=List[LMSReportRow], tags=["LMS"])
def get_lms_reporting(user=Depends(require_staff)):
    """Master report of all enrollments and progress (Staff only)"""
    uid, models = get_odoo_models()
    enrollments = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel.partner', 'search_read',
        [], {'fields': ['partner_id', 'channel_id', 'completion', 'write_date']}
    )
    return [LMSReportRow(
        student_id=e['partner_id'][0],
        student_name=e['partner_id'][1],
        course_id=e['channel_id'][0],
        course_name=e['channel_id'][1],
        completion=e.get('completion', 0.0),
        last_action=str(e.get('write_date'))
    ) for e in enrollments if e.get('partner_id') and e.get('channel_id')]

@app.get("/lms/my-courses", tags=["LMS"])
def get_my_courses(user=Depends(get_current_user)):
    """Get the list of LMS courses the current student is enrolled in"""
    partner_id = int(user.get("sub"))
    uid, models = get_odoo_models()
    enrollments = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel.partner', 'search_read',
        [[['partner_id', '=', partner_id]]], {'fields': ['channel_id', 'completion']}
    )
    return [{"course_id": e['channel_id'][0], "course_name": e['channel_id'][1], "completion": e.get('completion', 0)} for e in enrollments if e.get('channel_id')]

@app.get("/lms/my-progress/{channel_id}", response_model=LMSProgress, tags=["LMS"])
def get_my_progress(channel_id: int, user=Depends(get_current_user)):
    """Get the current student's progress in a specific LMS course"""
    partner_id = int(user.get("sub"))
    uid, models = get_odoo_models()
    enrollment = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel.partner', 'search_read',
        [[['channel_id', '=', channel_id], ['partner_id', '=', partner_id]]],
        {'fields': ['channel_id', 'completion'], 'limit': 1}
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Not enrolled in this course")
    channel = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel', 'read',
        [channel_id], {'fields': ['name', 'total_slides']}
    )
    e = enrollment[0]
    ch = channel[0]
    completion = e.get('completion', 0)
    total = ch.get('total_slides', 0)
    completed = round((completion / 100) * total) if total else 0
    return LMSProgress(channel_id=channel_id, channel_name=ch['name'], completion=completion, slides_completed=completed, total_slides=total)

# ===========================================================================
# --- Quiz Endpoints (slide.question, slide.answer) ---
# ===========================================================================

@app.get("/lms/slides/{slide_id}/quiz", tags=["Quiz"])
def get_quiz(slide_id: int, user=Depends(get_current_user)):
    """Get quiz questions for a specific slide"""
    uid, models = get_odoo_models()
    questions = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.question', 'search_read',
        [[['slide_id', '=', slide_id]]], {'fields': ['id', 'question', 'answer_ids']}
    )
    if not questions:
        raise HTTPException(status_code=404, detail="No quiz questions found for this slide")
    result = []
    for q in questions:
        answers = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.answer', 'read',
            [q['answer_ids']], {'fields': ['id', 'value']}
        )
        result.append({"id": q['id'], "question": q['question'], "answers": [{"id": a['id'], "value": a['value']} for a in answers]})
    return result

@app.post("/lms/slides/{slide_id}/quiz/submit", tags=["Quiz"])
def submit_quiz(slide_id: int, submission: QuizSubmission, user=Depends(get_current_user)):
    """Submit quiz answers and get score"""
    uid, models = get_odoo_models()
    questions = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.question', 'search_read',
        [[['slide_id', '=', slide_id]]], {'fields': ['id', 'answer_ids']}
    )
    if not questions:
        raise HTTPException(status_code=404, detail="No quiz found for this slide")
    correct = 0
    total = len(questions)
    for q in questions:
        correct_answers = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.answer', 'search_read',
            [[['question_id', '=', q['id']], ['is_correct', '=', True]]], {'fields': ['id']}
        )
        correct_ids = {a['id'] for a in correct_answers}
        submitted = next((s['answer_id'] for s in submission.answers if s.get('question_id') == q['id']), None)
        if submitted in correct_ids:
            correct += 1
    score = round((correct / total) * 100, 1) if total else 0
    return {"slide_id": slide_id, "score": score, "correct": correct, "total": total, "passed": score >= 70}

# ===========================================================================
# --- Progress / Completion Endpoints ---
# ===========================================================================

@app.post("/lms/slides/{slide_id}/complete", tags=["Progress"])
def mark_slide_complete(slide_id: int, user=Depends(get_current_user)):
    """Mark a slide/lesson as completed for the current student"""
    partner_id = int(user.get("sub"))
    uid, models = get_odoo_models()
    existing = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.slide.partner', 'search',
        [[['slide_id', '=', slide_id], ['partner_id', '=', partner_id]]]
    )
    if existing:
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.slide.partner', 'write',
            [existing, {'completed': True}]
        )
        return {"status": "updated", "message": "Slide already tracked, marked as complete"}
    models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.slide.partner', 'create', [{
        'slide_id': slide_id,
        'partner_id': partner_id,
        'completed': True,
    }])
    return {"status": "success", "message": "Slide marked as completed"}

# ===========================================================================
# --- Utility / Product Courses ---
# ===========================================================================

@app.get("/courses", response_model=List[Course], tags=["Courses"])
def list_courses(user=Depends(get_current_user)):
    """List product-based IT courses from Odoo"""
    uid, models = get_odoo_models()
    categ_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'search', [[['name', '=', 'IT Courses']]])
    if not categ_ids:
        return []
    data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.product', 'search_read',
        [[['categ_id', 'in', categ_ids]]], {'fields': ['id', 'name', 'list_price']}
    )
    return [Course(id=c['id'], name=c['name'], price=c['list_price']) for c in data]

# ===========================================================================
# --- Dashboard Endpoints ---
# ===========================================================================

@app.get("/dashboard/stats", tags=["Dashboard"])
def get_school_stats(user=Depends(get_current_user)):
    """Returns a high-level overview of the school system"""
    uid, models = get_odoo_models()
    
    student_tag = get_student_tag_id(models, uid)
    teacher_tag = get_teacher_tag_id(models, uid)
    
    return {
        "total_students": models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_count', [[['category_id', 'in', [student_tag]]]]),
        "total_teachers": models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search_count', [[['category_id', 'in', [teacher_tag]]]]),
        "lms_courses": models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel', 'search_count', [[]]),
        "total_enrollments": models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel.partner', 'search_count', [[]])
    }

@app.get("/", tags=["Root"])
def root():
    return {"message": "Welcome to School Management API v2.0 — Odoo Integrated", "docs": "/docs"}

# --- Customer Support Endpoints (Agent Escalation) ---

@app.post("/support/ticket", tags=["Customer Support"])
def create_support_ticket(ticket: SupportTicket):
    """Creates a support ticket in Odoo. Used by WhatsApp Agent for escalation."""
    uid, models = get_odoo_models()
    
    # 1. Ensure Support Project exists
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'School Support']]])
    if not project_ids:
        project_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'create', [{'name': 'School Support'}])
    else:
        project_id = project_ids[0]

    # 2. Create the ticket (Task)
    task_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'create', [{
        'name': f"[{ticket.issue_type}] {ticket.customer_name}",
        'project_id': project_id,
        'description': f"Phone: {ticket.phone}\nIssue: {ticket.message}\nRelated ID: {ticket.related_id or 'N/A'}",
        'priority': ticket.priority
    }])
    
    return {"status": "ticket_created", "ticket_id": task_id, "message": "School administration has been notified."}

@app.get("/support/my-tickets", tags=["Customer Support"])
def list_my_tickets(phone: str):
    """Fetch status of all school support tickets associated with a phone number"""
    uid, models = get_odoo_models()
    project_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', 'School Support']]])
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
