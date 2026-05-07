import os
import xmlrpc.client
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

FIRST_NAMES_MALE = ["Muhammad", "Ahmed", "Ali", "Omar", "Usman", "Hamza", "Hassan", "Hussain", "Bilal", "Zaid", "Mustafa", "Ibrahim", "Yahya", "Zakariya", "Yousaf", "Abdullah", "Abdul Rahman", "Sajid", "Tariq", "Imran"]
FIRST_NAMES_FEMALE = ["Fatima", "Zainab", "Aisha", "Mariam", "Khadija", "Sara", "Zoya", "Amna", "Hafsa", "Summaya", "Rumaisa", "Eshal", "Anaya", "Hoorain", "Noor", "Sana", "Iqra", "Bushra", "Nadia", "Farah"]
LAST_NAMES = ["Khan", "Ahmed", "Ali", "Hassan", "Hussain", "Shah", "Malik", "Sheikh", "Qureshi", "Siddiqui", "Abbasi", "Raza", "Naqvi", "Javed", "Iqbal", "Butt", "Dar", "Guijar", "Chaudhry", "Mughal"]

IT_SUBJECTS = [
    "Mobile App Development (Flutter)", "React Native Expo", "DevOps Engineering", 
    "Blockchain Technology", "UI/UX Design", "Digital Marketing", 
    "Software Quality Assurance", "Ethical Hacking", "Data Engineering",
    "Internet of Things (IoT)", "Game Development (Unity 3D)", "AR/VR Development"
]

def seed_large_data():
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        print("Connected to Odoo for Large Scale Seeding...")

        # 1. Get/Create Categories
        student_cat_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'search', [[['name', '=', 'Student']]])
        student_cat = student_cat_ids[0] if student_cat_ids else models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'create', [{'name': 'Student'}])

        teacher_cat_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'search', [[['name', '=', 'Teacher']]])
        teacher_cat = teacher_cat_ids[0] if teacher_cat_ids else models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner.category', 'create', [{'name': 'Teacher'}])

        course_categ_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'search', [[['name', '=', 'IT Courses']]])
        course_categ_id = course_categ_ids[0] if course_categ_ids else models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.category', 'create', [{'name': 'IT Courses'}])

        # 2. Add More Teachers
        print("Adding more Teachers...")
        for subject in IT_SUBJECTS[:8]:
            fname = random.choice(FIRST_NAMES_MALE + FIRST_NAMES_FEMALE)
            lname = random.choice(LAST_NAMES)
            name = f"{fname} {lname}"
            models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
                'name': name,
                'function': subject,
                'email': f"{fname.lower()}.{lname.lower()}@school.pk",
                'category_id': [(4, teacher_cat)]
            }])
        print("Teachers added.")

        # 3. Add More Course Products & LMS Channels
        print("Adding more IT Course Products & eLearning Channels...")
        for subject in IT_SUBJECTS:
            # Create the Product (for Sale)
            models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'product.product', 'create', [{
                'name': f"Professional {subject} Course",
                'list_price': random.randint(100, 500) * 100.0,
                'categ_id': course_categ_id,
                'type': 'service'
            }])
            
            # Create the eLearning Channel (for Dashboard)
            models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel', 'create', [{
                'name': f"Professional {subject} Mastery",
                'description': f"Comprehensive training on {subject}",
                'is_published': True,
                'visibility': 'public',
                'enroll': 'public'
            }])
        print("Products and Channels added.")

        # 4. Get LMS Channels for enrollment
        lms_channel_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel', 'search', [[]])
        if not lms_channel_ids:
            # Create at least one if none exist
            cid = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel', 'create', [{'name': 'General IT Introduction', 'is_published': True}])
            lms_channel_ids = [cid]

        # 5. Add 500 Students & Randomly Enroll them in LMS
        print("Generating 500 Students and enrolling them in LMS courses...")
        for i in range(1, 501):
            gender = random.choice(['m', 'f'])
            fname = random.choice(FIRST_NAMES_MALE if gender == 'm' else FIRST_NAMES_FEMALE)
            lname = random.choice(LAST_NAMES)
            name = f"{fname} {lname}"
            student_ref = f"STU{str(i).zfill(3)}"
            
            # Create Student Partner
            s_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
                'name': name,
                'ref': student_ref,
                'email': f"{fname.lower()}{i}@pk.edu",
                'category_id': [(4, student_cat)]
            }])
            
            # Randomly enroll in 1-2 LMS courses
            enroll_channels = random.sample(lms_channel_ids, k=random.randint(1, min(2, len(lms_channel_ids))))
            for channel_id in enroll_channels:
                models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'slide.channel.partner', 'create', [{
                    'channel_id': channel_id,
                    'partner_id': s_id,
                }])
            
            if i % 100 == 0:
                print(f"Created {i} students...")

        print("\nSuccessfully seeded 500 students with Pakistani names, more teachers, and IT courses!")

    except Exception as e:
        print(f"Error during large seeding: {e}")

if __name__ == "__main__":
    seed_large_data()
