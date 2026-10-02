import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

os.makedirs("test_samples", exist_ok=True)

# 1. Comprehensive Medical Report with Patient Info, Diagnoses, Conditions, Symptoms, Labs, Medications
c1 = canvas.Canvas(os.path.join("test_samples", "sample_comprehensive_report.pdf"), pagesize=letter)
c1.setFont("Helvetica-Bold", 16)
c1.drawString(50, 750, "ST. JUDE REGIONAL MEDICAL CENTER")
c1.setFont("Helvetica-Bold", 12)
c1.drawString(50, 730, "CLINICAL EVALUATION & LABORATORY REPORT")

c1.setFont("Helvetica", 10)
c1.drawString(50, 700, "Patient Name: Robert M. Chen")
c1.drawString(300, 700, "Patient ID: MRN-55219")
c1.drawString(50, 685, "Age: 58 Years")
c1.drawString(180, 685, "Gender: Male")
c1.drawString(300, 685, "DOB: 12/04/1966")
c1.drawString(50, 670, "Phone: (555) 987-6543")
c1.drawString(300, 670, "Email: r.chen@email.com")
c1.drawString(50, 655, "Attending Physician: Dr. Amanda Vance, MD")
c1.drawString(300, 655, "Report Date: 18-Oct-2024")

c1.setFont("Helvetica-Bold", 11)
c1.drawString(50, 625, "CHIEF COMPLAINTS & REPORTED SYMPTOMS:")
c1.setFont("Helvetica", 10)
c1.drawString(50, 610, "Patient reports persistent dry cough and mild generalized fatigue for two weeks. Denies chest pain or shortness of breath.")

c1.setFont("Helvetica-Bold", 11)
c1.drawString(50, 580, "PAST MEDICAL HISTORY:")
c1.setFont("Helvetica", 10)
c1.drawString(50, 565, "Longstanding Type 2 Diabetes Mellitus (managed for 7 years), Mild Essential Hypertension.")

c1.setFont("Helvetica-Bold", 11)
c1.drawString(50, 535, "DOCUMENTED DIAGNOSIS:")
c1.setFont("Helvetica", 10)
c1.drawString(50, 520, "1. Acute Upper Respiratory Tract Infection")
c1.drawString(50, 505, "2. Type 2 Diabetes Mellitus")

c1.setFont("Helvetica-Bold", 11)
c1.drawString(50, 475, "CLINICAL FINDINGS & PHYSICAL EXAMINATION:")
c1.setFont("Helvetica", 10)
c1.drawString(50, 460, "Blood Pressure: 138/88 mmHg. Bilateral breath sounds clear. Mild pharyngeal erythema.")

c1.setFont("Helvetica-Bold", 11)
c1.drawString(50, 430, "LABORATORY RESULTS:")
c1.setFont("Helvetica-Bold", 9)
c1.drawString(50, 415, "Test Description              Result       Unit         Reference Range   Status")
c1.setFont("Helvetica", 9)
c1.drawString(50, 400, "Hemoglobin                     13.8         g/dL         13.0 - 17.0       Normal")
c1.drawString(50, 385, "Fasting Blood Glucose          154          mg/dL        70 - 99           High")
c1.drawString(50, 370, "HbA1c                          7.4          %            4.0 - 5.6         High")
c1.drawString(50, 355, "Serum Creatinine               1.0          mg/dL        0.6 - 1.3         Normal")
c1.drawString(50, 340, "Total Cholesterol              220          mg/dL        < 200             High")
c1.drawString(50, 325, "HDL Cholesterol                42           mg/dL        > 40              Normal")
c1.drawString(50, 310, "Platelets                      245000       /µL          150000 - 450000   Normal")

c1.setFont("Helvetica-Bold", 11)
c1.drawString(50, 280, "CURRENT MEDICATIONS:")
c1.setFont("Helvetica", 10)
c1.drawString(50, 265, "1. Metformin 500mg oral twice daily with meals for diabetes.")
c1.drawString(50, 250, "2. Lisinopril 10mg oral once daily in the morning.")

c1.setFont("Helvetica-Bold", 11)
c1.drawString(50, 220, "RECOMMENDATIONS & DOCTOR NOTES:")
c1.setFont("Helvetica", 10)
c1.drawString(50, 205, "Maintain hydration and rest for upper respiratory symptoms. Follow up HbA1c in 3 months.")
c1.save()

# 2. Report with NO medical conditions explicitly stated (Normal routine checkup)
c2 = canvas.Canvas(os.path.join("test_samples", "sample_healthy_checkup.pdf"), pagesize=letter)
c2.setFont("Helvetica-Bold", 14)
c2.drawString(50, 750, "METROPOLITAN WELLNESS CLINIC")
c2.setFont("Helvetica", 10)
c2.drawString(50, 730, "Patient Name: Maria Rodriguez")
c2.drawString(300, 730, "Patient ID: PID-10928")
c2.drawString(50, 715, "Age: 32 Years")
c2.drawString(180, 715, "Gender: Female")
c2.drawString(300, 715, "Date: 05-Sep-2024")
c2.setFont("Helvetica-Bold", 11)
c2.drawString(50, 680, "ROUTINE ANNUAL HEALTH SCREENING")
c2.setFont("Helvetica", 10)
c2.drawString(50, 665, "Patient presents for annual preventive exam. Asymptomatic. No complaints.")
c2.drawString(50, 650, "No chronic medical conditions documented. No documented diagnoses.")
c2.drawString(50, 620, "Hemoglobin: 13.5 g/dL (Reference: 12.0 - 15.5 g/dL) - Normal")
c2.drawString(50, 605, "Glucose: 88 mg/dL (Reference: 70 - 99 mg/dL) - Normal")
c2.drawString(50, 590, "Creatinine: 0.8 mg/dL (Reference: 0.6 - 1.1 mg/dL) - Normal")
c2.drawString(50, 560, "Current Medications: None. No medications prescribed.")
c2.drawString(50, 530, "Doctor Notes: Routine follow-up in one year.")
c2.save()

# 3. Empty PDF (0 bytes or blank page)
c3 = canvas.Canvas(os.path.join("test_samples", "sample_blank_page.pdf"), pagesize=letter)
c3.showPage()
c3.save()

with open(os.path.join("test_samples", "sample_empty_zero_bytes.pdf"), "wb") as f:
    pass

with open(os.path.join("test_samples", "sample_not_a_pdf.txt"), "w") as f:
    f.write("This is a plain text file, not a PDF.")

print("Test sample PDFs created successfully in test_samples/")
