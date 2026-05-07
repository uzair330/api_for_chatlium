# School Management API — Documentation v2.0

> **API Base URL:** `http://localhost:8001`
> **Interactive Docs:** `http://localhost:8001/docs`
> **Odoo Backend:** `http://localhost:8069`
> **Integration:** 100% Real-time Odoo XML-RPC

---

## 🏗️ System Architecture

```
Client (App/WhatsApp)
       │
       ▼
FastAPI Bridge (Port 8001)   ──►   Odoo 18.0 (Port 8069)
 - JWT Authentication                - res.partner (Students/Teachers)
 - Role-Based Access                 - slide.channel (LMS Courses)
 - XML-RPC calls                     - slide.slide (Lessons)
                                     - slide.channel.partner (Enrollments)
                                     - slide.question/answer (Quizzes)
                                     - slide.slide.partner (Progress)
```

---

## 🔐 Authentication

All protected endpoints require:
```
Authorization: Bearer <TOKEN>
```

### Roles
| Role | Login Via | Access Level |
|------|-----------|-------------|
| `staff` | Odoo credentials (`res.users`) | Full CRUD, admin operations |
| `student` | Student ID + Email (`res.partner`) | Read own data, enroll, track progress |

---

### `POST /token`
**Staff / Admin Login** — Validates against Odoo's real user database.

**Request Body:**
```json
{
  "username": "uzair330@gmail.com",
  "password": "your_password"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### `POST /student/login`
**Student Login** — Authenticates using Student ID and Email from Odoo contacts.

**Request Body:**
```json
{
  "student_id": "STU001",
  "email": "zainab1@pk.edu"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### `POST /refresh`
**Refresh Token Exchange** — Exchanges a valid Refresh Token for a new set of Access and Refresh tokens.

**Headers:**
```
Authorization: Bearer <REFRESH_TOKEN>
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### `GET /me`
Returns the currently authenticated user's details decoded from the JWT token.

**Sample Response (Student):**
```json
{
  "sub": "19",
  "name": "Zainab Bibi",
  "student_id": "STU001",
  "role": "student"
}
```

---

## 👨‍🎓 Students (`res.partner`)

> All student endpoints require authentication. Write operations require the `staff` role.

### `GET /students`
List all students (paginated).

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `skip` | int | `0` | Records to skip |
| `limit` | int | `50` | Max records to return |

**Sample Response:**
```json
[
  {"id": 19, "name": "Zainab Bibi", "student_id": "STU001", "email": "zainab1@pk.edu", "phone": null},
  {"id": 20, "name": "Omar Farooq", "student_id": "STU002", "email": "omar2@pk.edu", "phone": null}
]
```

---

### `GET /students/{student_id}`
Get a single student's profile by their Odoo ID.

---

### `POST /students` ⚠️ Staff Only
Create a new student in Odoo.

**Request Body:**
```json
{
  "name": "Muhammad Bilal",
  "student_id": "STU507",
  "email": "bilal507@pk.edu",
  "phone": "+92300123456"
}
```

---

### `PUT /students/{student_id}` ⚠️ Staff Only
Update a student's details. Only fields provided will be updated.

**Request Body:**
```json
{
  "email": "new_email@pk.edu",
  "phone": "+92311999888"
}
```

---

### `DELETE /students/{student_id}` ⚠️ Staff Only
Archives (soft-deletes) the student in Odoo. The record is not permanently deleted.

---

## 👨‍🏫 Teachers (`res.partner`)

> All teacher endpoints require authentication. Creating a teacher requires the `staff` role.

### `GET /teachers`
List all teachers with their subject specializations.

**Sample Response:**
```json
[
  {"id": 16, "name": "Muhammad Ali", "subject": "Full Stack Development", "email": "ali@school.pk"},
  {"id": 17, "name": "Fatima Zahra", "subject": "Data Science & AI", "email": "fatima@school.pk"}
]
```

---

### `GET /teachers/{teacher_id}`
Get a single teacher's profile by their Odoo ID.

---

### `POST /teachers` ⚠️ Staff Only
Create a new teacher in Odoo.

**Request Body:**
```json
{
  "name": "Dr. Khalid Mahmood",
  "subject": "Network Engineering",
  "email": "khalid@school.pk"
}
```

---

## 📚 LMS Courses (`slide.channel`)

> Powered by Odoo's eLearning module (`website_slides`).

### `GET /lms/courses`
List all eLearning courses from Odoo.

**Sample Response:**
```json
[
  {"id": 1, "name": "Python Programming for Beginners", "total_slides": 0, "is_published": true},
  {"id": 2, "name": "Modern Web Apps with FastAPI", "total_slides": 0, "is_published": true}
]
```

---

### `GET /lms/courses/{channel_id}`
Get full details of a single course, including member count and description.

---

### `GET /lms/courses/{channel_id}/content`
List all lessons and slides in a course.

**Sample Response:**
```json
[
  {"id": 5, "name": "Introduction to Variables", "slide_type": "presentation", "is_preview": true},
  {"id": 6, "name": "Control Flow", "slide_type": "video", "is_preview": false}
]
```

---

### `GET /lms/courses/{channel_id}/content/{slide_id}`
Get the full details of a single lesson/slide within a course.

---

### `POST /lms/courses/{channel_id}/enroll`
Enroll the currently logged-in student into the specified course.

**Sample Response:**
```json
{"status": "success", "enroll_id": 120, "message": "Enrollment successful"}
```

---

### `DELETE /lms/courses/{channel_id}/unenroll`
Unenroll the currently logged-in student from a course.

---

### `GET /lms/courses/{channel_id}/members` ⚠️ Staff Only
List all students enrolled in a specific course.

**Sample Response:**
```json
[
  {"id": 19, "name": "Zainab Bibi", "email": "zainab1@pk.edu"},
  {"id": 20, "name": "Omar Farooq", "email": "omar2@pk.edu"}
]
```

---

## 📊 Dashboard & Stats

### `GET /dashboard/stats`
Returns a high-level overview of the school system.

**Sample Response:**
```json
{
  "total_students": 506,
  "total_teachers": 38,
  "lms_courses": 14,
  "total_enrollments": 842
}
```

---

## 📊 Progress Tracking

### `GET /lms/my-courses`
Get the list of all courses the current student is enrolled in, along with completion percentages.

**Sample Response:**
```json
[
  {"course_id": 1, "course_name": "Python Programming for Beginners", "completion": 35.5},
  {"course_id": 2, "course_name": "Modern Web Apps with FastAPI", "completion": 0.0}
]
```

---

### `GET /lms/my-progress/{channel_id}`
Get detailed progress for the current student in a specific course.

**Sample Response:**
```json
{
  "channel_id": 1,
  "channel_name": "Python Programming for Beginners",
  "completion": 35.5,
  "slides_completed": 4,
  "total_slides": 12
}
```

---

### `POST /lms/slides/{slide_id}/complete`
Mark a specific lesson/slide as completed for the current student.

**Sample Response:**
```json
{"status": "success", "message": "Slide marked as completed"}
```

---

## 📝 Quizzes (`slide.question`, `slide.answer`)

### `GET /lms/slides/{slide_id}/quiz`
Retrieve all quiz questions for a specific slide.

**Sample Response:**
```json
[
  {
    "id": 1,
    "question": "What is a Python list?",
    "answers": [
      {"id": 1, "value": "A mutable sequence"},
      {"id": 2, "value": "An immutable tuple"},
      {"id": 3, "value": "A dictionary key"}
    ]
  }
]
```

---

### `POST /lms/slides/{slide_id}/quiz/submit`
Submit answers for a quiz and get an instant score.

**Request Body:**
```json
{
  "answers": [
    {"question_id": 1, "answer_id": 1}
  ]
}
```

**Sample Response:**
```json
{
  "slide_id": 5,
  "score": 100.0,
  "correct": 1,
  "total": 1,
  "passed": true
}
```

> A score of **70% or above** is considered a pass.

---

## 🎓 Product-Based Courses

### `GET /courses`
List IT courses defined as Odoo **products** under the `IT Courses` category. These represent purchasable/bookable course products rather than eLearning content.

---

## ⚙️ Environment Configuration

All configuration is managed via the `.env` file in `School_api/`.

| Variable | Description |
|----------|-------------|
| `ODOO_URL` | URL of the Odoo instance (e.g., `http://web:8069`) |
| `ODOO_DB` | Target Odoo database name (e.g., `admin`) |
| `ODOO_USER` | Service account username |
| `ODOO_PASSWORD` | Service account password |
| `JWT_SECRET` | Secret key used to sign JWT tokens |

---

## 🚀 Running the API

**With Docker Compose (Recommended):**
```bash
docker compose up
```

**Locally (for development):**
```bash
cd School_api
uv run uvicorn main:app --reload --port 8001
```

**Seed initial data:**
```bash
# Initial seed (3 students, 3 teachers, 3 courses)
docker compose exec school-api uv run seed_data.py

# Large seed (500 students, more teachers & courses)
docker compose exec school-api uv run seed_data_large.py
```

---

## 🔒 Role-Based Access Summary

| Endpoint | Student | Staff |
|----------|---------|-------|
| Login, `/me` | ✅ | ✅ |
| `GET /students`, `GET /teachers` | ✅ | ✅ |
| `POST/PUT/DELETE /students` | ❌ | ✅ |
| `POST /teachers` | ❌ | ✅ |
| `GET /lms/courses` | ✅ | ✅ |
| Enroll / Unenroll | ✅ | ✅ |
| `GET /lms/courses/{id}/members` | ❌ | ✅ |
| My courses & progress | ✅ | ✅ |
| Quiz submit & slide complete | ✅ | ✅ |
