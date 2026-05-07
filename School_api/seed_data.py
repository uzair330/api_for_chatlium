import os
import xmlrpc.client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

def seed_school_data():
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        print("Connected to Odoo for Pakistan-themed IT School Seeding...")

        # 1. Create Partner Categories (Tags)
        student_cat_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'search', [[['name', '=', 'Student']]])
        if not student_cat_ids:
            student_cat = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'create', [{'name': 'Student'}])
        else:
            student_cat = student_cat_ids[0]

        teacher_cat_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'search', [[['name', '=', 'Teacher']]])
        if not teacher_cat_ids:
            teacher_cat = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'create', [{'name': 'Teacher'}])
        else:
            teacher_cat = teacher_cat_ids[0]

        # 2. Create Teachers (IT Related)
        teachers = [
            {'name': 'Muhammad Ali', 'subject': 'Full Stack Development', 'email': 'ali@school.pk'},
            {'name': 'Fatima Zahra', 'subject': 'Data Science & AI', 'email': 'fatima@school.pk'},
            {'name': 'Ahmed Hassan', 'subject': 'Cybersecurity', 'email': 'ahmed@school.pk'},
        ]
        for t in teachers:
            t_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
                'name': t['name'],
                'function': t['subject'],
                'email': t['email'],
                'category_id': [(4, teacher_cat)]
            }])
            print(f"Created Teacher: {t['name']} (ID: {t_id})")

        # 3. Create Students
        students = [
            {'name': 'Zainab Bibi', 'ref': 'STU001', 'email': 'zainab@pk.edu'},
            {'name': 'Omar Farooq', 'ref': 'STU002', 'email': 'omar@pk.edu'},
            {'name': 'Aisha Siddiqua', 'ref': 'STU003', 'email': 'aisha@pk.edu'},
        ]
        for s in students:
            s_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
                'name': s['name'],
                'ref': s['ref'],
                'email': s['email'],
                'category_id': [(4, student_cat)]
            }])
            print(f"Created Student: {s['name']} (ID: {s_id})")

        # 4. Create Courses (Products)
        course_categ_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'search', [[['name', '=', 'IT Courses']]])
        if not course_categ_ids:
            course_categ_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'create', [{'name': 'IT Courses'}])
        else:
            course_categ_id = course_categ_ids[0]

        it_courses = [
            {'name': 'Web Development with Python & Odoo', 'price': 15000.0},
            {'name': 'Machine Learning Mastery', 'price': 25000.0},
            {'name': 'Cloud Computing (AWS/Azure)', 'price': 20000.0},
        ]
        for c in it_courses:
            c_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.product', 'create', [{
                'name': c['name'],
                'list_price': c['price'],
                'categ_id': course_categ_id,
                'type': 'service'
            }])
            print(f"Created IT Course Product: {c['name']} (ID: {c_id})")

        # 5. Create LMS Channels (slide.channel)
        lms_courses = [
            {'name': 'Python Programming for Beginners (Urdu/English)', 'description': 'Master Python from scratch.'},
            {'name': 'Modern Web Apps with FastAPI', 'description': 'Learn to build fast APIs.'},
        ]
        for lms in lms_courses:
            lms_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel', 'create', [{
                'name': lms['name'],
                'description': lms['description'],
                'is_published': True,
                'visibility': 'public',
                'enroll': 'public'
            }])
            print(f"Created LMS Course: {lms['name']} (ID: {lms_id})")

        print("\nPakistan-themed IT School data seeding successful!")

    except Exception as e:
        print(f"Error seeding school data: {e}")

if __name__ == "__main__":
    seed_school_data()
