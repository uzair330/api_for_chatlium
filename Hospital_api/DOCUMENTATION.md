# Hospital Management API v1.0

This is a production-ready Hospital Management API integrated with **Odoo 19.0**. It handles clinical workflows, patient management, and doctor scheduling.

---

## 🔐 Authentication & Security

The API uses **JWT (JSON Web Tokens)** for security. 
- **Access Tokens**: Valid for 60 minutes.
- **Refresh Tokens**: Valid for 7 days.

### `POST /token`
**Login** — Authenticate staff using Odoo credentials.

**Request Body:**
```json
{
  "username": "api_user",
  "password": "api_password_123"
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
**Token Refresh** — Get a new access token using a refresh token.

**Headers:**
`Authorization: Bearer <REFRESH_TOKEN>`

---

## 👥 Personnel Management

### `GET /patients`
List all patients from Odoo. Supports pagination.
- `skip`: Records to skip (default 0)
- `limit`: Records to return (default 20)

### `POST /patients`
Create a new patient record.

---

### `GET /doctors`
List all doctors and their specialties from Odoo.

---

## 🏥 Clinical Workflows

### `GET /appointments`
List all medical appointments and checkups.

### `POST /appointments`
Book a new appointment.
**Request Body:**
```json
{
  "patient_id": 1093,
  "doctor_id": 6,
  "name": "General Checkup",
  "start": "2026-05-10T10:00:00",
  "stop": "2026-05-10T11:00:00"
}
```

---

### `GET /departments`
List all medical departments (Cardiology, Radiology, etc.).

### `GET /lab-reports`
List all patient lab test results.

### `GET /opd`
View Outpatient Department visit records and diagnoses.

### `GET /operations`
List all scheduled and completed surgical operations.

---

## 📊 Dashboard

### `GET /dashboard/stats`
Get a high-level overview of the hospital system.

**Response:**
```json
{
  "patients": 35,
  "doctors": 28,
  "appointments": 25
}
```

---

## 🛠 Tech Stack
- **Framework**: FastAPI (Python 3.12)
- **Odoo Engine**: XML-RPC
- **Package Manager**: UV
- **Server**: Uvicorn
