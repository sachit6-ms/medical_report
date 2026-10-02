import os
import re
import json
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import pymupdf
import ollama
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# ---------------------------------------------------------------------------
# APP CONFIGURATION
# ---------------------------------------------------------------------------

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
REPORT_FOLDER = os.path.join(BASE_DIR, "generated_reports")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["REPORT_FOLDER"] = REPORT_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

OLLAMA_MODEL = "llama3.2:3b"

DISCLAIMER_TEXT = (
    "This system summarizes information present in the uploaded medical report "
    "for educational purposes. It is not a medical diagnosis and should not replace "
    "evaluation by a qualified healthcare professional."
)

# Standard reference ranges for fallback comparison when reports lack them
STANDARD_RANGES = {
    "Hemoglobin": {"low": 12.0, "high": 17.0, "unit": "g/dL"},
    "WBC": {"low": 4000, "high": 11000, "unit": "/µL"},
    "Platelets": {"low": 150000, "high": 450000, "unit": "/µL"},
    "RBC": {"low": 4.0, "high": 6.0, "unit": "million/µL"},
    "Glucose": {"low": 70, "high": 99, "unit": "mg/dL"},
    "Fasting Blood Glucose": {"low": 70, "high": 99, "unit": "mg/dL"},
    "Creatinine": {"low": 0.6, "high": 1.3, "unit": "mg/dL"},
    "Serum Creatinine": {"low": 0.6, "high": 1.3, "unit": "mg/dL"},
    "Urea": {"low": 15, "high": 45, "unit": "mg/dL"},
    "Blood Urea": {"low": 15, "high": 45, "unit": "mg/dL"},
    "BUN": {"low": 7, "high": 20, "unit": "mg/dL"},
    "Total Cholesterol": {"low": 0, "high": 200, "unit": "mg/dL"},
    "HDL": {"low": 40, "high": 100, "unit": "mg/dL"},
    "HDL Cholesterol": {"low": 40, "high": 100, "unit": "mg/dL"},
    "LDL": {"low": 0, "high": 100, "unit": "mg/dL"},
    "LDL Cholesterol": {"low": 0, "high": 100, "unit": "mg/dL"},
    "Triglycerides": {"low": 0, "high": 150, "unit": "mg/dL"},
    "TSH": {"low": 0.4, "high": 4.0, "unit": "µIU/mL"},
    "HbA1c": {"low": 4.0, "high": 5.6, "unit": "%"}
}


# ---------------------------------------------------------------------------
# PDF TEXT EXTRACTION (PyMuPDF)
# ---------------------------------------------------------------------------

def extract_pdf_text(filepath):
    """
    Extracts text from PDF using PyMuPDF.
    Returns: (text, error_message)
    """
    text_parts = []
    try:
        doc = pymupdf.open(filepath)

        if doc.page_count == 0:
            doc.close()
            return "", "The uploaded PDF contains no pages."

        if doc.is_encrypted:
            doc.close()
            return "", "The uploaded PDF is password-protected and cannot be read."

        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_text = page.get_text()
            if page_text:
                text_parts.append(page_text)

        doc.close()

        full_text = "\n".join(text_parts).strip()
        # Clean null bytes
        full_text = full_text.replace("\x00", "")
        # Normalize excessive inline whitespace
        full_text = re.sub(r"[ \t]+", " ", full_text)

        if len(full_text.strip()) < 15:
            return "", (
                "No extractable text found in the PDF. This may be an image-only "
                "or scanned document. Please upload a digital text-based medical PDF."
            )

        return full_text, None

    except Exception as e:
        return "", f"Error reading PDF file: {str(e)}"


# ---------------------------------------------------------------------------
# DETERMINISTIC PATIENT & SENSITIVE INFORMATION DETECTION
# ---------------------------------------------------------------------------

def detect_patient_and_sensitive_info(text):
    """
    Detects patient information fields and sensitive identification markers.
    Returns: (patient_info_dict, sensitive_info_dict)
    """
    patient_info = {
        "name": "Not available",
        "patient_id": "Not available",
        "mrn": "Not available",
        "age": "Not available",
        "dob": "Not available",
        "gender": "Not available",
        "phone": "Not available",
        "email": "Not available",
        "address": "Not available",
        "hospital": "Not available",
        "doctor": "Not available",
        "report_date": "Not available"
    }

    # Name patterns
    name_match = re.search(
        r"(?:Patient\s*Name|Patient|Pt\s*Name|Name)\s*[:\-]\s*([A-Za-z\.\s]+?)(?=\s{2,}|\n|,|\bAge\b|\bDOB\b|\bSex\b|\bGender\b|\bID\b|$)",
        text,
        re.IGNORECASE
    )
    if name_match:
        val = name_match.group(1).strip()
        if len(val) > 1 and not re.search(r"\b(Report|Date|Doctor|Hospital|Lab|Test|Clinical)\b", val, re.IGNORECASE):
            patient_info["name"] = val

    # Patient ID / MRN
    id_match = re.search(
        r"(?:Patient\s*ID|PID|UHID|Record\s*No\.?)\s*[:\-]?\s*([A-Za-z0-9\-_]+)",
        text,
        re.IGNORECASE
    )
    if id_match:
        patient_info["patient_id"] = id_match.group(1).strip()

    mrn_match = re.search(
        r"(?:MRN|Medical\s*Record\s*(?:Number|No\.?))\s*[:\-]?\s*([A-Za-z0-9\-_]+)",
        text,
        re.IGNORECASE
    )
    if mrn_match:
        patient_info["mrn"] = mrn_match.group(1).strip()
        if patient_info["patient_id"] == "Not available":
            patient_info["patient_id"] = mrn_match.group(1).strip()

    # Age
    age_match = re.search(
        r"(?:Age)\s*[:\-]?\s*([0-9]{1,3}(?:\s*(?:years?|yrs?|y))?)",
        text,
        re.IGNORECASE
    )
    if age_match:
        patient_info["age"] = age_match.group(1).strip()

    # DOB
    dob_match = re.search(
        r"(?:DOB|Date\s*of\s*Birth|Birth\s*Date)\s*[:\-]?\s*([0-9]{1,2}[\/\-\.][0-9]{1,2}[\/\-\.][0-9]{2,4})",
        text,
        re.IGNORECASE
    )
    if dob_match:
        patient_info["dob"] = dob_match.group(1).strip()

    # Gender / Sex
    gender_match = re.search(
        r"(?:Gender|Sex)\s*[:\-]?\s*(Male|Female|M|F|Other)",
        text,
        re.IGNORECASE
    )
    if gender_match:
        g = gender_match.group(1).strip().capitalize()
        patient_info["gender"] = "Male" if g in ["M", "Male"] else ("Female" if g in ["F", "Female"] else g)

    # Phone / Mobile
    phone_match = re.search(
        r"(?:Phone|Mobile|Contact|Tel)\s*[:\-]?\s*([+]?[0-9\s\-\(\)\.]{7,16})",
        text,
        re.IGNORECASE
    )
    if not phone_match:
        phone_match = re.search(r"(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", text)
    if phone_match:
        p_val = phone_match.group(1).strip()
        if len(re.sub(r"\D", "", p_val)) >= 7:
            patient_info["phone"] = p_val

    # Email
    email_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    if email_match:
        patient_info["email"] = email_match.group(1).strip()

    # Address
    addr_match = re.search(
        r"(?:Address|Addr)\s*[:\-]\s*([^\n\r]+)",
        text,
        re.IGNORECASE
    )
    if addr_match:
        patient_info["address"] = addr_match.group(1).strip()

    # Hospital / Clinic
    hosp_match = re.search(
        r"(?:Hospital|Clinic|Center|Healthcare|Laboratory|Lab)\s*[:\-]?\s*([^\n\r]+)",
        text,
        re.IGNORECASE
    )
    if hosp_match:
        h_val = hosp_match.group(1).strip()
        if len(h_val) > 2 and len(h_val) < 80:
            patient_info["hospital"] = h_val

    # Doctor / Physician
    doc_match = re.search(
        r"(?:Dr\.?|Doctor|Physician|Referred\s*By|Ref\s*By)\s*[:\-]?\s*([^\n\r]+)",
        text,
        re.IGNORECASE
    )
    if doc_match:
        d_val = doc_match.group(1).strip()
        if len(d_val) > 2 and len(d_val) < 60:
            patient_info["doctor"] = d_val if d_val.lower().startswith("dr") else f"Dr. {d_val}"

    # Report Date
    date_match = re.search(
        r"(?:Report\s*Date|Date|Collected|Sample\s*Date)\s*[:\-]?\s*([0-9]{1,2}[\/\-\.][0-9]{1,2}[\/\-\.][0-9]{2,4}(?:\s+[0-9]{1,2}:[0-9]{2}(?:\s*[AP]M)?)?)",
        text,
        re.IGNORECASE
    )
    if date_match:
        patient_info["report_date"] = date_match.group(1).strip()

    # Determine Sensitive Categories
    categories = {
        "Patient Name": "Detected" if patient_info["name"] != "Not available" else "Not detected",
        "Patient ID": "Detected" if patient_info["patient_id"] != "Not available" else "Not detected",
        "Medical Record Number (MRN)": "Detected" if patient_info["mrn"] != "Not available" else "Not detected",
        "Phone Number": "Detected" if patient_info["phone"] != "Not available" else "Not detected",
        "Email": "Detected" if patient_info["email"] != "Not available" else "Not detected",
        "Address": "Detected" if patient_info["address"] != "Not available" else "Not detected",
        "Date of Birth": "Detected" if patient_info["dob"] != "Not available" else "Not detected",
    }

    any_detected = any(v == "Detected" for v in categories.values())

    sensitive_info = {
        "detected": any_detected,
        "summary": "YES" if any_detected else "NO",
        "categories": categories
    }

    return patient_info, sensitive_info


# ---------------------------------------------------------------------------
# SENSITIVE DATA REDACTION HELPER
# ---------------------------------------------------------------------------

def apply_masking_to_data(data, mask=True):
    """
    Returns a copy of the data with sensitive values masked with [REDACTED]
    if mask=True. Does NOT modify original file.
    """
    if not mask:
        return data

    masked_data = json.loads(json.dumps(data))
    p_info = masked_data.get("patient_information", {})

    original_name = p_info.get("name", "")
    original_id = p_info.get("patient_id", "")
    original_phone = p_info.get("phone", "")
    original_email = p_info.get("email", "")

    sensitive_fields = ["name", "patient_id", "mrn", "phone", "email", "address", "dob"]
    for field in sensitive_fields:
        if field in p_info and p_info[field] != "Not available" and p_info[field] != "Not stated in the report.":
            p_info[field] = "[REDACTED]"

    masked_data["patient_information"] = p_info

    # Also redact specific patient identifiers from overall_summary
    summary = masked_data.get("overall_summary", "")
    for val in [original_name, original_id, original_phone, original_email]:
        if val and val not in ["Not available", "Not stated in the report."]:
            if len(val) > 2:
                summary = re.sub(re.escape(val), "[REDACTED]", summary, flags=re.IGNORECASE)
    masked_data["overall_summary"] = summary
    masked_data["is_masked"] = True
    return masked_data


# ---------------------------------------------------------------------------
# RULE-BASED LABORATORY PARAMETER EXTRACTOR (ENHANCED FALLBACK)
# ---------------------------------------------------------------------------

def extract_rule_based_lab_data(text):
    """
    Extracts laboratory parameters and classifies status using report's own
    ranges or standard medical reference intervals.
    """
    results = []

    for test_name, ref in STANDARD_RANGES.items():
        pattern = rf"(?:{re.escape(test_name)})\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
            except ValueError:
                continue

            # Check if this test was already added
            if any(r["test"].lower() == test_name.lower() for r in results):
                continue

            # Determine status based on standard reference range
            if val < ref["low"]:
                status = "LOW"
            elif val > ref["high"]:
                status = "HIGH"
            else:
                status = "NORMAL"

            results.append({
                "test": test_name,
                "value": str(val),
                "unit": ref["unit"],
                "reference_range": f"{ref['low']} - {ref['high']}",
                "status": status
            })

    return results


# ---------------------------------------------------------------------------
# DETERMINISTIC MEDICATION EXTRACTOR
# ---------------------------------------------------------------------------

def extract_medications_from_text(text):
    """
    Deterministic regex-based extractor for medications explicitly mentioned in the report.
    Returns: list of dicts with keys name, dose, frequency, route, duration
    """
    meds = []
    med_match = re.search(
        r"(?:CURRENT\s*MEDICATIONS?|MEDICATIONS?\s*MENTIONED|MEDICATIONS?|PRESCRIPTIONS?|Rx)\s*[:\-]?\s*\n?((?:(?!\n[A-Z\s]{4,}:)[\s\S])+)",
        text,
        re.IGNORECASE
    )

    if med_match:
        lines = med_match.group(1).strip().split("\n")
        for line in lines:
            clean_l = re.sub(r"^[\d\.\-\*\s]+", "", line).strip()
            if not clean_l or clean_l.lower().startswith(("none", "no medications", "denies", "nil")):
                continue
            if len(clean_l) < 3 or clean_l.lower().startswith(("recommend", "doctor", "follow", "maintain")):
                continue

            # Extract Dose
            dose_m = re.search(r"(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?|tablets?|capsules?))\b", clean_l, re.IGNORECASE)
            dose = dose_m.group(1) if dose_m else "Not stated."

            # Extract Frequency
            freq_m = re.search(r"\b(once\s*daily|twice\s*daily|thrice\s*daily|daily|bid|tid|qid|q\d+h|every\s*\d+\s*hours?|as\s*needed|prn|in\s*the\s*morning|at\s*bedtime)\b", clean_l, re.IGNORECASE)
            freq = freq_m.group(1) if freq_m else "Not stated."

            # Extract Route
            route_m = re.search(r"\b(oral|po|iv|subcutaneous|topical|inhalation|intramuscular|im)\b", clean_l, re.IGNORECASE)
            route = route_m.group(1) if route_m else "Not stated."

            # Clean name
            name_part = clean_l.split(" for ")[0].split(" - ")[0].strip()

            meds.append({
                "name": name_part,
                "dose": dose,
                "frequency": freq,
                "route": route,
                "duration": "Not stated."
            })

    return meds


# ---------------------------------------------------------------------------
# OLLAMA MEDICAL REPORT ANALYZER
# ---------------------------------------------------------------------------

def check_ollama_status():
    """Checks if Ollama service is reachable and model is available."""
    try:
        models_response = ollama.list()
        models = getattr(models_response, "models", [])
        if not models and isinstance(models_response, dict):
            models = models_response.get("models", [])

        model_names = [getattr(m, "model", "") or m.get("model", "") or m.get("name", "") for m in models]
        target_found = any(OLLAMA_MODEL in name for name in model_names)

        return True, target_found, None
    except Exception as e:
        return False, False, str(e)


def analyze_with_ollama(extracted_text, patient_info):
    """
    Sends the medical report text to Ollama (llama3.2:3b) with strict medical
    safety constraints and parses the structured JSON response.
    """
    system_prompt = (
        "You are a medical report summarization assistant.\n"
        "Analyze ONLY the information contained in the supplied medical report.\n"
        "Do not diagnose the patient.\n"
        "Do not invent medical conditions.\n"
        "Do not invent symptoms.\n"
        "Do not invent medications.\n"
        "Do not provide treatment recommendations.\n"
        "Do not modify numerical laboratory values.\n"
        "If information is missing, write 'Not stated in the report.'\n"
        "Return valid JSON only.\n\n"
        "Strict Medical Rules:\n"
        "1. 'documented_diagnoses': Extract ONLY diagnoses explicitly written under Diagnosis, "
        "Impression, Assessment, Conclusion, or explicitly stated as a diagnosed condition. "
        "Do NOT invent diagnoses. Do NOT convert abnormal laboratory values into diagnoses "
        "(e.g., elevated glucose is NOT diabetes unless explicitly diagnosed). If none, return [].\n"
        "2. 'medical_conditions': Extract medical conditions explicitly mentioned in the report "
        "(e.g., history of hypertension, asthma, diabetes). If none, return [].\n"
        "3. 'symptoms': Extract ONLY symptoms explicitly reported by the patient or noted in the report "
        "(e.g., fever, cough, chest pain, fatigue). If none, return [].\n"
        "4. 'clinical_findings': Extract explicit clinical findings (e.g., blood pressure reading, "
        "abnormal ECG finding, physical examination finding, imaging finding, laboratory abnormality). "
        "Do not convert findings into diagnoses.\n"
        "5. 'abnormal_findings': List abnormal test results or abnormal findings explicitly identified.\n"
        "6. 'normal_findings': List normal test results or normal findings explicitly identified.\n"
        "7. 'laboratory_results': Array of objects with keys: 'test', 'value', 'unit', 'reference_range', 'status'. "
        "Status MUST be one of: 'NORMAL', 'HIGH', 'LOW', 'ABNORMAL', or 'UNKNOWN'. "
        "If the report provides its own reference range, prefer that range. If no reference range exists, "
        "write 'Reference range not provided.' and status 'UNKNOWN'. Do not guess.\n"
        "8. 'medications': Array of objects with keys: 'name', 'dose', 'frequency', 'route', 'duration'. "
        "Extract medications explicitly mentioned. If a subfield is not available, write 'Not stated.' "
        "Do NOT recommend medications. Do NOT change dosage. If none, return [].\n"
        "9. 'overall_summary': Concise factual summary of information explicitly present in the report.\n"
        "10. 'important_notes': Notes, recommendations, or follow-up instructions explicitly written by the doctor in the report. "
        "Do NOT invent advice.\n"
    )

    user_prompt = f"""Medical Report Text:
\"\"\"
{extracted_text[:6000]}
\"\"\"

Respond with a single JSON object matching this exact schema:
{{
  "patient_information": {{
    "name": "{patient_info.get('name', 'Not available')}",
    "age": "{patient_info.get('age', 'Not available')}",
    "gender": "{patient_info.get('gender', 'Not available')}",
    "patient_id": "{patient_info.get('patient_id', 'Not available')}",
    "report_date": "{patient_info.get('report_date', 'Not available')}"
  }},
  "documented_diagnoses": [],
  "medical_conditions": [],
  "symptoms": [],
  "clinical_findings": [],
  "abnormal_findings": [],
  "normal_findings": [],
  "laboratory_results": [
    {{
      "test": "",
      "value": "",
      "unit": "",
      "reference_range": "",
      "status": ""
    }}
  ],
  "medications": [
    {{
      "name": "",
      "dose": "",
      "frequency": "",
      "route": "",
      "duration": ""
    }}
  ],
  "overall_summary": "",
  "important_notes": []
}}
"""

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            format="json",
            options={
                "temperature": 0.1,
                "num_predict": 1200
            }
        )

        content = response["message"]["content"]
        parsed_json = clean_and_parse_json(content)
        return parsed_json, None

    except Exception as e:
        return None, str(e)


def clean_and_parse_json(content):
    """
    Safely extracts and parses JSON even if wrapped in markdown, accompanied by text,
    or slightly truncated. Guarantees application never crashes.
    """
    if not content:
        return None

    # 1. Direct parse attempt
    cleaned = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 2. Extract code block
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if code_match:
        try:
            return json.loads(code_match.group(1).strip())
        except Exception:
            pass

    # 3. Locate outer braces
    s_idx = content.find("{")
    e_idx = content.rfind("}")
    if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
        try:
            return json.loads(content[s_idx:e_idx + 1])
        except Exception:
            pass

    # 4. Robust regex recovery parser
    data = {
        "patient_information": {},
        "documented_diagnoses": [],
        "medical_conditions": [],
        "symptoms": [],
        "clinical_findings": [],
        "abnormal_findings": [],
        "normal_findings": [],
        "laboratory_results": [],
        "medications": [],
        "overall_summary": "",
        "important_notes": []
    }

    # Extract overall_summary
    sum_m = re.search(r'"overall_summary"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', content)
    if sum_m:
        data["overall_summary"] = sum_m.group(1)

    # Extract string lists
    for key in ["documented_diagnoses", "medical_conditions", "symptoms", "clinical_findings", "abnormal_findings", "normal_findings", "important_notes"]:
        match = re.search(rf'"{key}"\s*:\s*\[(.*?)\]', content, re.DOTALL)
        if match:
            items = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', match.group(1))
            data[key] = items

    # Extract laboratory_results
    labs_m = re.search(r'"laboratory_results"\s*:\s*\[(.*?)\]', content, re.DOTALL)
    if labs_m:
        obj_matches = re.findall(r'\{([^{}]+)\}', labs_m.group(1))
        labs = []
        for obj_str in obj_matches:
            test = re.search(r'"test"\s*:\s*"([^"]*)"', obj_str)
            val = re.search(r'"value"\s*:\s*"([^"]*)"', obj_str)
            unit = re.search(r'"unit"\s*:\s*"([^"]*)"', obj_str)
            ref = re.search(r'"reference_range"\s*:\s*"([^"]*)"', obj_str)
            stat = re.search(r'"status"\s*:\s*"([^"]*)"', obj_str)
            if test or val:
                labs.append({
                    "test": test.group(1) if test else "",
                    "value": val.group(1) if val else "",
                    "unit": unit.group(1) if unit else "",
                    "reference_range": ref.group(1) if ref else "",
                    "status": stat.group(1) if stat else "UNKNOWN"
                })
        data["laboratory_results"] = labs

    # Extract medications
    meds_m = re.search(r'"medications"\s*:\s*\[(.*?)\]', content, re.DOTALL)
    if meds_m:
        obj_matches = re.findall(r'\{([^{}]+)\}', meds_m.group(1))
        meds = []
        for obj_str in obj_matches:
            name = re.search(r'"name"\s*:\s*"([^"]*)"', obj_str)
            dose = re.search(r'"dose"\s*:\s*"([^"]*)"', obj_str)
            freq = re.search(r'"frequency"\s*:\s*"([^"]*)"', obj_str)
            route = re.search(r'"route"\s*:\s*"([^"]*)"', obj_str)
            dur = re.search(r'"duration"\s*:\s*"([^"]*)"', obj_str)
            if name:
                meds.append({
                    "name": name.group(1),
                    "dose": dose.group(1) if dose else "Not stated",
                    "frequency": freq.group(1) if freq else "Not stated",
                    "route": route.group(1) if route else "Not stated",
                    "duration": dur.group(1) if dur else "Not stated"
                })
        data["medications"] = meds

    if data["documented_diagnoses"] or data["laboratory_results"] or data["overall_summary"]:
        return data

    return None


# ---------------------------------------------------------------------------
# FALLBACK SYNTHESIS WHEN OLLAMA IS UNAVAILABLE OR RETURNS INVALID JSON
# ---------------------------------------------------------------------------

def generate_fallback_analysis(extracted_text, patient_info, sensitive_info):
    """
    Deterministic fallback when Ollama is unavailable or fails to return JSON.
    Guarantees the application never crashes and adheres to all separation rules.
    """
    rule_labs = extract_rule_based_lab_data(extracted_text)

    normal_findings = []
    abnormal_findings = []

    for item in rule_labs:
        if item["status"] == "NORMAL":
            normal_findings.append(f"{item['test']} is within normal limits ({item['value']} {item['unit']})")
        else:
            abnormal_findings.append(f"{item['test']} is {item['status'].lower()} ({item['value']} {item['unit']})")

    # Extract diagnoses section if present (stopping at next major uppercase section header)
    diag_match = re.search(
        r"(?:DOCUMENTED\s*DIAGNOSIS|DIAGNOSIS|IMPRESSION|ASSESSMENT)\s*[:\-]?\s*\n?((?:(?!\n[A-Z\s]{4,}:)[\s\S])+)",
        extracted_text,
        re.IGNORECASE
    )
    documented_diagnoses = []
    if diag_match:
        for line in diag_match.group(1).strip().split("\n"):
            clean_l = re.sub(r"^[\d\.\-\*\s]+", "", line).strip()
            if clean_l and len(clean_l) > 3 and not clean_l.lower().startswith(("recommend", "clinical")):
                documented_diagnoses.append(clean_l)

    # Extract symptoms section if present
    symptom_match = re.search(
        r"(?:CHIEF\s*COMPLAINTS?|COMPLAINTS?|SYMPTOMS?|REPORTED\s*SYMPTOMS?)\s*[:\-]?\s*\n?((?:(?!\n[A-Z\s]{4,}:)[\s\S])+)",
        extracted_text,
        re.IGNORECASE
    )
    symptoms = []
    if symptom_match:
        for line in symptom_match.group(1).strip().split("\n"):
            clean_s = re.sub(r"^[\d\.\-\*\s]+", "", line).strip()
            if clean_s and len(clean_s) > 3:
                symptoms.append(clean_s)

    # Extract medications deterministically
    medications = extract_medications_from_text(extracted_text)

    # Build summary
    summary_parts = []
    if documented_diagnoses:
        summary_parts.append(f"Documented diagnoses in the report include: {', '.join(documented_diagnoses)}.")
    if abnormal_findings:
        summary_parts.append(f"Abnormal findings reported: {'; '.join(abnormal_findings)}.")
    if normal_findings:
        summary_parts.append(f"Normal parameters: {', '.join([item['test'] for item in rule_labs if item['status'] == 'NORMAL'])}.")
    if not summary_parts:
        summary_parts.append("Report extracted successfully. No critical diagnostic abnormalities explicitly flagged.")

    summary_parts.append(DISCLAIMER_TEXT)

    return {
        "patient_information": patient_info,
        "documented_diagnoses": documented_diagnoses,
        "medical_conditions": documented_diagnoses,
        "symptoms": symptoms if symptoms else [],
        "clinical_findings": abnormal_findings if abnormal_findings else ["No acute clinical findings explicitly documented."],
        "abnormal_findings": abnormal_findings,
        "normal_findings": normal_findings,
        "laboratory_results": rule_labs,
        "medications": medications,
        "overall_summary": " ".join(summary_parts),
        "important_notes": ["Generated via deterministic rule engine. Review with original lab report."]
    }


# ---------------------------------------------------------------------------
# REPORTLAB PDF GENERATION
# ---------------------------------------------------------------------------

def generate_pdf_report(data, output_path, mask_sensitive=False):
    """
    Generates a professional, medical-grade PDF report using ReportLab.
    Includes all separated medical condition categories and the disclaimer.
    """
    # Apply masking if requested
    active_data = apply_masking_to_data(data, mask=mask_sensitive)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1e1b4b"),
        alignment=0
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748b")
    )

    h2_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#312e81"),
        spaceBefore=12,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1e293b")
    )

    disclaimer_style = ParagraphStyle(
        "DisclaimerText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#991b1b")
    )

    elements = []

    # 1. Header Banner
    header_table = Table(
        [
            [
                Paragraph("AI-Based Medical Report Analysis", title_style),
                Paragraph(
                    f"Generated: {datetime.now().strftime('%d-%b-%Y %H:%M')}<br/>"
                    f"Confidentiality: {'[REDACTED VIEW]' if mask_sensitive else 'Standard'}",
                    subtitle_style
                )
            ]
        ],
        colWidths=[330, 190]
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4)
    ]))
    elements.append(header_table)

    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#4f46e5"), spaceAfter=10))

    # 2. Medical Safety Disclaimer Box
    disclaimer_data = [
        [
            Paragraph(
                f"<b>MEDICAL DISCLAIMER:</b> {DISCLAIMER_TEXT}",
                disclaimer_style
            )
        ]
    ]
    disclaimer_table = Table(disclaimer_data, colWidths=[522])
    disclaimer_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef2f2")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#f87171")),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
    ]))
    elements.append(disclaimer_table)
    elements.append(Spacer(1, 12))

    # 3. Patient Information & Sensitive Status Table
    p_info = active_data.get("patient_information", {})
    s_info = active_data.get("sensitive_information", {})

    patient_grid = [
        [
            Paragraph("<b>Patient Name:</b>", body_style),
            Paragraph(str(p_info.get("name", "Not available")), body_style),
            Paragraph("<b>Patient ID / MRN:</b>", body_style),
            Paragraph(str(p_info.get("patient_id", p_info.get("mrn", "Not available"))), body_style),
        ],
        [
            Paragraph("<b>Age:</b>", body_style),
            Paragraph(str(p_info.get("age", "Not available")), body_style),
            Paragraph("<b>Gender:</b>", body_style),
            Paragraph(str(p_info.get("gender", "Not available")), body_style),
        ],
        [
            Paragraph("<b>Date of Birth:</b>", body_style),
            Paragraph(str(p_info.get("dob", "Not available")), body_style),
            Paragraph("<b>Report Date:</b>", body_style),
            Paragraph(str(p_info.get("report_date", "Not available")), body_style),
        ],
        [
            Paragraph("<b>Doctor:</b>", body_style),
            Paragraph(str(p_info.get("doctor", "Not available")), body_style),
            Paragraph("<b>Sensitive Info:</b>", body_style),
            Paragraph(
                f"{'Detected (MASKED)' if mask_sensitive else ('Detected (YES)' if s_info.get('detected') else 'NO')}",
                body_style
            ),
        ]
    ]

    p_table = Table(patient_grid, colWidths=[110, 151, 110, 151])
    p_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
    ]))

    elements.append(Paragraph("Patient Information", h2_style))
    elements.append(p_table)
    elements.append(Spacer(1, 10))

    # 4. Documented Diagnoses & Medical Conditions
    diagnoses = active_data.get("documented_diagnoses", [])
    conditions = active_data.get("medical_conditions", [])

    elements.append(Paragraph("Documented Diagnoses & Medical Conditions", h2_style))
    diag_items = []
    if diagnoses:
        for d in diagnoses:
            diag_items.append(Paragraph(f"• <b>Diagnosis:</b> {d}", body_style))
    else:
        diag_items.append(Paragraph("• <i>No documented diagnoses explicitly stated in the report.</i>", body_style))

    if conditions and conditions != diagnoses:
        for c in conditions:
            if c not in diagnoses:
                diag_items.append(Paragraph(f"• <b>Known Condition:</b> {c}", body_style))

    diag_table = Table([[item] for item in diag_items], colWidths=[522])
    diag_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#86efac")),
        ("PADDING", (0, 0), (-1, -1), 6)
    ]))
    elements.append(diag_table)
    elements.append(Spacer(1, 10))

    # 5. Symptoms & Clinical Findings
    symptoms = active_data.get("symptoms", [])
    findings = active_data.get("clinical_findings", [])

    elements.append(Paragraph("Reported Symptoms & Clinical Findings", h2_style))
    symp_text = ", ".join(symptoms) if symptoms else "No symptoms explicitly stated in the report."
    find_text = "; ".join(findings) if findings else "No acute clinical findings explicitly noted."

    sf_grid = [
        [Paragraph("<b>Reported Symptoms:</b>", body_style), Paragraph(symp_text, body_style)],
        [Paragraph("<b>Clinical Findings:</b>", body_style), Paragraph(find_text, body_style)]
    ]
    sf_table = Table(sf_grid, colWidths=[130, 392])
    sf_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP")
    ]))
    elements.append(sf_table)
    elements.append(Spacer(1, 10))

    # 6. Laboratory Results Table
    lab_results = active_data.get("laboratory_results", [])
    elements.append(Paragraph("Laboratory Results & Status Classification", h2_style))

    if lab_results:
        lab_table_data = [
            [
                Paragraph("<b>Test Name</b>", body_style),
                Paragraph("<b>Value</b>", body_style),
                Paragraph("<b>Unit</b>", body_style),
                Paragraph("<b>Reference Range</b>", body_style),
                Paragraph("<b>Status</b>", body_style)
            ]
        ]

        for item in lab_results:
            st = str(item.get("status", "UNKNOWN")).upper()
            status_color = "#16a34a" if st == "NORMAL" else ("#dc2626" if st in ["HIGH", "LOW", "ABNORMAL"] else "#64748b")
            status_para = Paragraph(f"<font color='{status_color}'><b>{st}</b></font>", body_style)

            lab_table_data.append([
                Paragraph(str(item.get("test", "Not stated")), body_style),
                Paragraph(str(item.get("value", "")), body_style),
                Paragraph(str(item.get("unit", "")), body_style),
                Paragraph(str(item.get("reference_range", "Reference range not provided.")), body_style),
                status_para
            ])

        lab_table = Table(lab_table_data, colWidths=[150, 70, 70, 142, 90])
        lab_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
        ]))
        elements.append(lab_table)
    else:
        elements.append(Paragraph("<i>No discrete laboratory results detected in the report.</i>", body_style))

    elements.append(Spacer(1, 10))

    # 7. Medications / Treatments Mentioned
    medications = active_data.get("medications", [])
    elements.append(Paragraph("Medications & Treatments Mentioned", h2_style))

    if medications:
        med_rows = [
            [
                Paragraph("<b>Medication Name</b>", body_style),
                Paragraph("<b>Dose</b>", body_style),
                Paragraph("<b>Frequency</b>", body_style),
                Paragraph("<b>Route</b>", body_style),
                Paragraph("<b>Duration</b>", body_style)
            ]
        ]

        for m in medications:
            if isinstance(m, dict):
                med_rows.append([
                    Paragraph(str(m.get("name") or m.get("Name") or "Not stated"), body_style),
                    Paragraph(str(m.get("dose") or m.get("Dose") or "Not stated"), body_style),
                    Paragraph(str(m.get("frequency") or m.get("Frequency") or "Not stated"), body_style),
                    Paragraph(str(m.get("route") or m.get("Route") or "Not stated"), body_style),
                    Paragraph(str(m.get("duration") or m.get("Duration") or "Not stated"), body_style)
                ])
            else:
                med_rows.append([
                    Paragraph(str(m), body_style),
                    Paragraph("Not stated", body_style),
                    Paragraph("Not stated", body_style),
                    Paragraph("Not stated", body_style),
                    Paragraph("Not stated", body_style)
                ])

        med_table = Table(med_rows, colWidths=[150, 80, 100, 80, 112])
        med_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
        ]))
        elements.append(med_table)
    else:
        elements.append(Paragraph("<i>No medications or treatments explicitly stated in the report.</i>", body_style))

    elements.append(Spacer(1, 10))

    # 8. AI Medical Summary & Important Notes
    elements.append(Paragraph("AI Medical Summary", h2_style))
    summary_text = active_data.get("overall_summary", "Summary not generated.")
    elements.append(Paragraph(summary_text, body_style))

    notes = active_data.get("important_notes", [])
    if notes:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("<b>Important Notes / Recommendations:</b>", body_style))
        for note in notes:
            elements.append(Paragraph(f"• {note}", body_style))

    # Build document
    doc.build(elements)


# ---------------------------------------------------------------------------
# FLASK WEB ROUTES
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    """Renders the main dashboard interface."""
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    """
    Accepts PDF file upload, extracts and cleans text, detects patient & sensitive
    info, sends relevant text to local Ollama (Llama 3.2 3B), and returns
    structured separated medical conditions.
    """
    if "file" not in request.files:
        return jsonify({
            "success": False,
            "message": "No file selected. Please select a medical PDF file to upload."
        }), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "Please select a valid PDF file."
        }), 400

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".pdf"):
        return jsonify({
            "success": False,
            "message": "Invalid file format. Only PDF (.pdf) files are supported."
        }), 400

    unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

    try:
        file.save(filepath)

        # 1. Text extraction
        extracted_text, extract_err = extract_pdf_text(filepath)
        if extract_err:
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({
                "success": False,
                "message": extract_err
            }), 400

        # 2. Patient and sensitive information detection
        patient_info, sensitive_info = detect_patient_and_sensitive_info(extracted_text)

        # 3. Check Ollama availability
        ollama_ok, model_found, ollama_err = check_ollama_status()

        analysis_result = None
        ollama_status_msg = "Analysis completed."

        if not ollama_ok:
            # Safe fallback if Ollama service is not running
            analysis_result = generate_fallback_analysis(extracted_text, patient_info, sensitive_info)
            ollama_status_msg = "Ollama is not running. Please start Ollama and make sure llama3.2:3b is installed."
        elif not model_found:
            # Safe fallback if model is not yet pulled
            analysis_result = generate_fallback_analysis(extracted_text, patient_info, sensitive_info)
            ollama_status_msg = (
                f"Model '{OLLAMA_MODEL}' was not found in Ollama. Run 'ollama pull {OLLAMA_MODEL}'. "
                "The system used deterministic rule-based analysis as a safe fallback."
            )
        else:
            # 4. Ollama LLM Inference
            llm_result, llm_err = analyze_with_ollama(extracted_text, patient_info)
            if llm_result:
                analysis_result = llm_result
                # Reconcile patient info from heuristics if LLM missed any
                llm_p = analysis_result.get("patient_information", {})
                for k, v in patient_info.items():
                    if k not in llm_p or llm_p[k] in ["", "Not available", "Not stated in the report."]:
                        llm_p[k] = v
                analysis_result["patient_information"] = llm_p

                # Ensure medications are complemented from text if LLM array is empty
                if not analysis_result.get("medications"):
                    detected_meds = extract_medications_from_text(extracted_text)
                    if detected_meds:
                        analysis_result["medications"] = detected_meds
            else:
                # Fallback if Ollama returned invalid JSON
                analysis_result = generate_fallback_analysis(extracted_text, patient_info, sensitive_info)
                ollama_status_msg = (
                    "Ollama response could not be parsed as valid JSON. "
                    "Rule-based deterministic extraction was used safely."
                )

        # Attach sensitive info and raw text
        analysis_result["sensitive_information"] = sensitive_info
        analysis_result["raw_text"] = extracted_text
        analysis_result["filename"] = filename
        analysis_result["saved_filename"] = unique_filename
        analysis_result["disclaimer"] = DISCLAIMER_TEXT
        analysis_result["ollama_status_message"] = ollama_status_msg

        # Count metrics
        lab_results = analysis_result.get("laboratory_results", [])
        total_parameters = len(lab_results)
        normal_count = sum(1 for item in lab_results if str(item.get("status", "")).upper() == "NORMAL")
        abnormal_count = sum(1 for item in lab_results if str(item.get("status", "")).upper() in ["HIGH", "LOW", "ABNORMAL"])

        analysis_result["total_parameters"] = total_parameters
        analysis_result["normal_count"] = normal_count
        analysis_result["abnormal_count"] = abnormal_count

        return jsonify({
            "success": True,
            "data": analysis_result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Server encountered an error processing report: {str(e)}"
        }), 500


@app.route("/download_report", methods=["POST"])
def download_report():
    """
    Generates and returns the downloadable PDF report.
    Supports sensitive information masking.
    """
    req_payload = request.get_json(silent=True)
    if not req_payload:
        return jsonify({"success": False, "message": "Invalid request payload."}), 400

    report_data = req_payload.get("data", req_payload)
    mask_sensitive = bool(req_payload.get("mask_sensitive", False))

    report_id = uuid.uuid4().hex[:8]
    output_filename = f"Medical_Report_Analysis_{report_id}.pdf"
    output_filepath = os.path.join(app.config["REPORT_FOLDER"], output_filename)

    try:
        generate_pdf_report(report_data, output_filepath, mask_sensitive=mask_sensitive)

        if not os.path.exists(output_filepath):
            return jsonify({"success": False, "message": "Failed to create PDF report."}), 500

        return send_file(
            output_filepath,
            as_attachment=True,
            download_name="AI_Medical_Report_Analysis.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error generating PDF report: {str(e)}"
        }), 500


# ---------------------------------------------------------------------------
# APPLICATION ENTRYPOINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )