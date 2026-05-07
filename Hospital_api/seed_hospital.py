import os
import xmlrpc.client
import random
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

def seed_hospital():
    print("Connecting to Odoo for Hospital Seeding...")
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

    # 1. Create Tags
    patient_tag = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'search', [[['name', '=', 'Patient']]])
    if not patient_tag:
        patient_tag = [models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'create', [{'name': 'Patient'}])]
    
    doctor_tag = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'search', [[['name', '=', 'Doctor']]])
    if not doctor_tag:
        doctor_tag = [models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'create', [{'name': 'Doctor'}])]

    # 2. Create Doctors
    doctor_names = ["Dr. Ali Khan", "Dr. Fatima Ahmed", "Dr. Hassan Raza", "Dr. Zainab Bibi"]
    specialties = ["Cardiology", "Neurology", "Pediatrics", "General Surgery"]
    doctor_ids = []
    
    for i in range(len(doctor_names)):
        d_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
            'name': doctor_names[i],
            'function': specialties[i],
            'category_id': [(4, doctor_tag[0])],
            'phone': f"+92-300-{random.randint(1000000, 9999999)}"
        }])
        doctor_ids.append(d_id)
    print(f"Created {len(doctor_ids)} Doctors.")

    # 3. Create Patients
    patient_names = ["Umar Sheikh", "Sana Gul", "Bilal Khan", "Ayesha Malik", "Kamran Akmal"]
    blood_groups = ["A+", "B+", "O-", "AB+", "A-"]
    patient_ids = []
    
    for i in range(len(patient_names)):
        p_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
            'name': patient_names[i],
            'ref': f"PAT-{1000 + i}",
            'category_id': [(4, patient_tag[0])],
            'comment': blood_groups[i],
            'phone': f"+92-321-{random.randint(1000000, 9999999)}"
        }])
        patient_ids.append(p_id)
    print(f"Created {len(patient_ids)} Patients.")

    # 4. Create Departments (Projects) - skip if already exist
    dept_names = ["Cardiology", "Neurology", "Pediatrics", "OPD", "Operations", "Lab Reports"]
    dept_map = {}
    for name in dept_names:
        existing = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'search', [[['name', '=', name]]])
        if existing:
            dept_map[name] = existing[0]
        else:
            d_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.project', 'create', [{'name': name}])
            dept_map[name] = d_id
    print(f"Departments ready: {list(dept_map.keys())}")

    # 5. Create Appointments (Calendar)
    for i in range(5):
        hour = 10 + i
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'calendar.event', 'create', [{
            'name': f"Checkup - {patient_names[i % len(patient_names)]}",
            'start': f"2026-05-10 {hour:02d}:00:00",
            'stop': f"2026-05-10 {hour:02d}:30:00",
            'partner_ids': [(6, 0, [patient_ids[i % len(patient_ids)], doctor_ids[i % len(doctor_ids)]])]
        }])
    print("Created 5 Sample Appointments.")

    # 6. Create Lab Reports (Tasks in Lab Reports Project)
    tests = ["Blood Test", "X-Ray", "MRI Scan", "COVID-19 Swab"]
    for i in range(4):
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'create', [{
            'name': tests[i],
            'project_id': dept_map["Lab Reports"],
            'partner_id': patient_ids[i % len(patient_ids)],
            'description': "Result: Normal / Clear",
        }])
    print("Created 4 Lab Reports.")

    # 7. Create OPD Records (Tasks in OPD Project)
    symptoms = ["Fever", "Cough", "Back Pain", "Headache"]
    for i in range(4):
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'create', [{
            'name': symptoms[i],
            'project_id': dept_map["OPD"],
            'partner_id': patient_ids[i % len(patient_ids)],
            'description': "Diagnosis: Viral Infection / Rest prescribed.",
        }])
    print("Created 4 OPD Records.")

    # 8. Create Operations (Tasks in Operations Project)
    ops = ["Appendix Removal", "Knee Surgery", "Eye LASIK", "Heart Stent"]
    for i in range(4):
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'project.task', 'create', [{
            'name': ops[i],
            'project_id': dept_map["Operations"],
            'partner_id': patient_ids[i % len(patient_ids)],
            'date_deadline': f"2026-05-12",
        }])
    print("Created 4 Operations.")

if __name__ == "__main__":
    seed_hospital()
