/**
 * AI-Based Medical Report Summarization & Condition Separation
 * Frontend Controller & Dynamic Clinical Dashboard
 */

let currentAnalysisData = null;
let isMasked = false;

// ---------------------------------------------------------------------------
// INITIALIZATION & DRAG-AND-DROP HANDLERS
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    setupDragAndDrop();
    setupFileInput();
});

function setupDragAndDrop() {
    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("fileInput");

    if (!dropZone || !fileInput) return;

    ["dragenter", "dragover"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add("drag-active");
        });
    });

    ["dragleave", "drop"].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove("drag-active");
        });
    });

    dropZone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleSelectedFile(files[0]);
        }
    });
}

function setupFileInput() {
    const fileInput = document.getElementById("fileInput");
    if (!fileInput) return;

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleSelectedFile(e.target.files[0]);
        }
    });
}

function handleSelectedFile(file) {
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".pdf")) {
        showStatusAlert("Invalid file format. Please upload a PDF file (.pdf).", "error");
        clearSelectedFile();
        return;
    }

    if (file.size > 16 * 1024 * 1024) {
        showStatusAlert("File size exceeds 16MB limit. Please upload a smaller PDF.", "error");
        clearSelectedFile();
        return;
    }

    const nameSpan = document.getElementById("selectedFileName");
    const sizeSpan = document.getElementById("selectedFileSize");
    const bar = document.getElementById("fileSelectionBar");
    const dropZone = document.getElementById("dropZone");

    if (nameSpan) nameSpan.textContent = file.name;
    if (sizeSpan) sizeSpan.textContent = formatFileSize(file.size);
    if (bar) bar.classList.remove("hidden");
    if (dropZone) dropZone.classList.add("hidden");

    hideStatusAlert();
}

function clearSelectedFile() {
    const fileInput = document.getElementById("fileInput");
    const bar = document.getElementById("fileSelectionBar");
    const dropZone = document.getElementById("dropZone");

    if (fileInput) fileInput.value = "";
    if (bar) bar.classList.add("hidden");
    if (dropZone) dropZone.classList.remove("hidden");
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

// ---------------------------------------------------------------------------
// REPORT ANALYSIS API CALL
// ---------------------------------------------------------------------------

async function analyzeReport() {
    const fileInput = document.getElementById("fileInput");
    if (!fileInput || !fileInput.files.length) {
        showStatusAlert("Please select or drop a medical PDF report first.", "warning");
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append("file", file);

    const analyzeBtn = document.getElementById("analyzeButton");
    const loading = document.getElementById("loadingIndicator");
    const resultsContainer = document.getElementById("resultsContainer");

    if (analyzeBtn) analyzeBtn.disabled = true;
    if (loading) loading.classList.remove("hidden");
    if (resultsContainer) resultsContainer.classList.add("hidden");
    hideStatusAlert();

    try {
        const response = await fetch("/analyze", {
            method: "POST",
            body: formData
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            const errorMsg = result.message || "Failed to analyze report.";
            showStatusAlert(errorMsg, "error");
            return;
        }

        currentAnalysisData = result.data;
        isMasked = false; // reset masking state for new report

        // Check if there was an Ollama status or warning message
        if (currentAnalysisData.ollama_status_message) {
            const isWarning = currentAnalysisData.ollama_status_message.includes("Ollama is not running") ||
                              currentAnalysisData.ollama_status_message.includes("not found");
            showStatusAlert(
                currentAnalysisData.ollama_status_message,
                isWarning ? "warning" : "info"
            );
        }

        // Render dashboard
        renderDashboard(currentAnalysisData, isMasked);

        if (resultsContainer) {
            resultsContainer.classList.remove("hidden");
            resultsContainer.scrollIntoView({ behavior: "smooth", block: "start" });
        }

    } catch (err) {
        console.error("Analysis error:", err);
        showStatusAlert(
            "An unexpected network or server error occurred while processing the report.",
            "error"
        );
    } finally {
        if (analyzeBtn) analyzeBtn.disabled = false;
        if (loading) loading.classList.add("hidden");
    }
}

// ---------------------------------------------------------------------------
// DASHBOARD RENDERING CONTROLLER
// ---------------------------------------------------------------------------

function renderDashboard(data, mask = false) {
    if (!data) return;

    renderStats(data);
    renderPatientInfo(data.patient_information, mask);
    renderSensitiveInfo(data.sensitive_information, mask);
    renderDiagnoses(data.documented_diagnoses);
    renderMedicalConditions(data.medical_conditions);
    renderSymptoms(data.symptoms);
    renderClinicalFindings(data.clinical_findings);
    renderLabResults(data.laboratory_results);
    renderNormalFindings(data.normal_findings);
    renderAbnormalFindings(data.abnormal_findings);
    renderMedications(data.medications);
    renderAiSummary(data.overall_summary);
    renderImportantNotes(data.important_notes);
    renderRawText(data.raw_text, data.patient_information, mask);
}

// 1. Stats Counters
function renderStats(data) {
    document.getElementById("statTotalParameters").textContent = data.total_parameters || 0;
    document.getElementById("statNormalCount").textContent = data.normal_count || 0;
    document.getElementById("statAbnormalCount").textContent = data.abnormal_count || 0;

    const diagnosesCount = (data.documented_diagnoses || []).length;
    const conditionsCount = (data.medical_conditions || []).length;
    document.getElementById("statConditionsCount").textContent = Math.max(diagnosesCount, conditionsCount);
}

// 2. Patient Information
function renderPatientInfo(info, mask = false) {
    const grid = document.getElementById("patientGrid");
    if (!grid) return;
    grid.innerHTML = "";

    const sensitiveKeys = ["name", "patient_id", "mrn", "dob", "phone", "email", "address"];

    const fieldLabels = {
        name: "Patient Name",
        patient_id: "Patient ID",
        mrn: "Medical Record No (MRN)",
        age: "Age",
        gender: "Gender / Sex",
        dob: "Date of Birth",
        phone: "Phone / Mobile",
        email: "Email Address",
        doctor: "Attending / Ref. Doctor",
        hospital: "Hospital / Healthcare Facility",
        report_date: "Report / Collection Date"
    };

    const keys = Object.keys(fieldLabels);

    keys.forEach(k => {
        let val = (info && info[k]) ? info[k] : "Not available";
        const isSensitive = sensitiveKeys.includes(k) && val !== "Not available" && val !== "Not stated in the report.";
        
        let displayVal = val;
        let isRedacted = false;

        if (mask && isSensitive) {
            displayVal = "[REDACTED]";
            isRedacted = true;
        }

        const item = document.createElement("div");
        item.className = "patient-item";
        item.innerHTML = `
            <div class="patient-key">${fieldLabels[k]}</div>
            <div class="patient-value ${isRedacted ? 'redacted' : ''}">${escapeHtml(displayVal)}</div>
        `;
        grid.appendChild(item);
    });
}

// 3. Sensitive Information & Masking
function renderSensitiveInfo(sensitive, mask = false) {
    const badge = document.getElementById("sensitiveDetectionBadge");
    const chipsGrid = document.getElementById("sensitiveCategoriesGrid");
    const toggleBtn = document.getElementById("maskToggleBtn");
    const btnText = document.getElementById("maskBtnText");

    const isDetected = sensitive && sensitive.detected;

    if (badge) {
        badge.className = isDetected ? "badge badge-yes" : "badge badge-no";
        badge.textContent = isDetected ? "Sensitive Data Detected: YES" : "Sensitive Data Detected: NO";
    }

    if (toggleBtn && btnText) {
        if (mask) {
            toggleBtn.classList.add("active-redaction");
            btnText.textContent = "Unmask Sensitive Information";
        } else {
            toggleBtn.classList.remove("active-redaction");
            btnText.textContent = "Mask Sensitive Information";
        }
    }

    if (chipsGrid) {
        chipsGrid.innerHTML = "";
        const categories = (sensitive && sensitive.categories) ? sensitive.categories : {};

        Object.entries(categories).forEach(([cat, status]) => {
            const isCatDetected = status === "Detected";
            const chip = document.createElement("div");
            chip.className = "chip-item";

            let statusLabel = status;
            if (mask && isCatDetected) {
                statusLabel = "MASKED [REDACTED]";
            }

            chip.innerHTML = `
                <span class="chip-label">${escapeHtml(cat)}</span>
                <span class="chip-status ${isCatDetected ? 'detected' : 'not-detected'}">
                    ${escapeHtml(statusLabel)}
                </span>
            `;
            chipsGrid.appendChild(chip);
        });
    }
}

// Toggle Sensitive Info Masking Button Handler
function toggleSensitiveMasking() {
    if (!currentAnalysisData) return;
    isMasked = !isMasked;
    renderDashboard(currentAnalysisData, isMasked);
}

// 4. Documented Diagnoses
function renderDiagnoses(diagnoses) {
    const list = document.getElementById("diagnosesList");
    if (!list) return;
    list.innerHTML = "";

    if (!diagnoses || diagnoses.length === 0) {
        list.innerHTML = `<li class="condition-empty">No documented diagnoses explicitly stated in the report.</li>`;
        return;
    }

    diagnoses.forEach(diag => {
        const li = document.createElement("li");
        li.className = "condition-item";
        li.innerHTML = `
            <span class="condition-bullet" style="background:#059669;"></span>
            <span><strong>Diagnosis:</strong> ${escapeHtml(diag)}</span>
        `;
        list.appendChild(li);
    });
}

// 5. Medical Conditions
function renderMedicalConditions(conditions) {
    const list = document.getElementById("conditionsList");
    if (!list) return;
    list.innerHTML = "";

    if (!conditions || conditions.length === 0) {
        list.innerHTML = `<li class="condition-empty">No medical conditions explicitly stated in the report.</li>`;
        return;
    }

    conditions.forEach(cond => {
        const li = document.createElement("li");
        li.className = "condition-item";
        li.innerHTML = `
            <span class="condition-bullet"></span>
            <span>${escapeHtml(cond)}</span>
        `;
        list.appendChild(li);
    });
}

// 6. Symptoms
function renderSymptoms(symptoms) {
    const list = document.getElementById("symptomsList");
    if (!list) return;
    list.innerHTML = "";

    if (!symptoms || symptoms.length === 0) {
        list.innerHTML = `<li class="condition-empty">No symptoms explicitly stated in the report.</li>`;
        return;
    }

    symptoms.forEach(sym => {
        const li = document.createElement("li");
        li.className = "condition-item";
        li.innerHTML = `
            <span class="condition-bullet" style="background:#e11d48;"></span>
            <span>${escapeHtml(sym)}</span>
        `;
        list.appendChild(li);
    });
}

// 7. Clinical Findings
function renderClinicalFindings(findings) {
    const list = document.getElementById("findingsList");
    if (!list) return;
    list.innerHTML = "";

    if (!findings || findings.length === 0) {
        list.innerHTML = `<li class="condition-empty">No acute clinical findings explicitly noted.</li>`;
        return;
    }

    findings.forEach(f => {
        const li = document.createElement("li");
        li.className = "condition-item";
        li.innerHTML = `
            <span class="condition-bullet" style="background:#0284c7;"></span>
            <span>${escapeHtml(f)}</span>
        `;
        list.appendChild(li);
    });
}

// 8. Laboratory Results Table
function renderLabResults(labs) {
    const tbody = document.getElementById("labResultsTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!labs || labs.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="condition-empty">
                    No discrete laboratory parameters detected from the uploaded report.
                </td>
            </tr>
        `;
        return;
    }

    labs.forEach(item => {
        const row = document.createElement("tr");

        const statusRaw = (item.status || "UNKNOWN").toUpperCase();
        let statusClass = "unknown";
        if (statusRaw === "NORMAL") statusClass = "normal";
        else if (statusRaw === "HIGH") statusClass = "high";
        else if (statusRaw === "LOW") statusClass = "low";
        else if (statusRaw === "ABNORMAL") statusClass = "abnormal";

        row.innerHTML = `
            <td><strong>${escapeHtml(item.test || "Not stated")}</strong></td>
            <td>${escapeHtml(String(item.value || ""))}</td>
            <td>${escapeHtml(item.unit || "")}</td>
            <td>${escapeHtml(item.reference_range || "Reference range not provided.")}</td>
            <td><span class="status-pill ${statusClass}">${escapeHtml(statusRaw)}</span></td>
        `;
        tbody.appendChild(row);
    });
}

// 9. Normal Findings
function renderNormalFindings(normals) {
    const list = document.getElementById("normalFindingsList");
    if (!list) return;
    list.innerHTML = "";

    if (!normals || normals.length === 0) {
        list.innerHTML = `<li class="condition-empty">No normal findings explicitly categorized.</li>`;
        return;
    }

    normals.forEach(item => {
        const li = document.createElement("li");
        li.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2.5">
                <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span>${escapeHtml(item)}</span>
        `;
        list.appendChild(li);
    });
}

// 10. Abnormal Findings
function renderAbnormalFindings(abnormals) {
    const list = document.getElementById("abnormalFindingsList");
    if (!list) return;
    list.innerHTML = "";

    if (!abnormals || abnormals.length === 0) {
        list.innerHTML = `<li class="condition-empty">No abnormal findings explicitly categorized.</li>`;
        return;
    }

    abnormals.forEach(item => {
        const li = document.createElement("li");
        li.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2.5">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span>${escapeHtml(item)}</span>
        `;
        list.appendChild(li);
    });
}

// 11. Medications / Treatments Mentioned
function renderMedications(meds) {
    const tbody = document.getElementById("medicationsTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!meds || meds.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="condition-empty">
                    No medications or treatments explicitly stated in the report.
                </td>
            </tr>
        `;
        return;
    }

    meds.forEach(m => {
        const row = document.createElement("tr");

        if (typeof m === "object" && m !== null) {
            row.innerHTML = `
                <td><strong>${escapeHtml(m.name || m.Name || "Not stated")}</strong></td>
                <td>${escapeHtml(m.dose || m.Dose || "Not stated")}</td>
                <td>${escapeHtml(m.frequency || m.Frequency || "Not stated")}</td>
                <td>${escapeHtml(m.route || m.Route || "Not stated")}</td>
                <td>${escapeHtml(m.duration || m.Duration || "Not stated")}</td>
            `;
        } else {
            row.innerHTML = `
                <td><strong>${escapeHtml(String(m))}</strong></td>
                <td>Not stated</td>
                <td>Not stated</td>
                <td>Not stated</td>
                <td>Not stated</td>
            `;
        }
        tbody.appendChild(row);
    });
}

// 12. AI Medical Summary
function renderAiSummary(summary) {
    const body = document.getElementById("aiSummaryBody");
    if (!body) return;
    body.textContent = summary || "AI summary not generated.";
}

// 13. Important Notes
function renderImportantNotes(notes) {
    const list = document.getElementById("importantNotesList");
    if (!list) return;
    list.innerHTML = "";

    if (!notes || notes.length === 0) {
        list.innerHTML = `<li class="condition-empty">No additional doctor notes or follow-up recommendations noted.</li>`;
        return;
    }

    notes.forEach(note => {
        const li = document.createElement("li");
        li.textContent = note;
        list.appendChild(li);
    });
}

// 14. Extracted Report Text
function renderRawText(text, patientInfo, mask = false) {
    const viewer = document.getElementById("rawTextViewer");
    if (!viewer) return;

    let displayText = text || "No text available.";

    if (mask && patientInfo) {
        // Redact detected specific values if present in raw text
        ["name", "patient_id", "mrn", "phone", "email"].forEach(k => {
            const val = patientInfo[k];
            if (val && val !== "Not available" && val.length > 2) {
                const escaped = val.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                displayText = displayText.replace(new RegExp(escaped, 'gi'), "[REDACTED]");
            }
        });
    }

    viewer.textContent = displayText;
}

function copyExtractedText() {
    const viewer = document.getElementById("rawTextViewer");
    if (!viewer) return;

    navigator.clipboard.writeText(viewer.textContent)
        .then(() => {
            showStatusAlert("Extracted report text copied to clipboard.", "info");
        })
        .catch(err => {
            console.error("Clipboard copy failed:", err);
        });
}

// ---------------------------------------------------------------------------
// 15. DOWNLOAD PDF REPORT
// ---------------------------------------------------------------------------

async function downloadPdfReport() {
    if (!currentAnalysisData) {
        showStatusAlert("Please analyze a report before downloading.", "warning");
        return;
    }

    const downloadBtn = document.getElementById("downloadReportBtn");
    if (downloadBtn) downloadBtn.disabled = true;

    try {
        const payload = {
            data: currentAnalysisData,
            mask_sensitive: isMasked
        };

        const response = await fetch("/download_report", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            showStatusAlert(errData.message || "Failed to generate PDF.", "error");
            return;
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = isMasked
            ? "AI_Medical_Report_Analysis_Redacted.pdf"
            : "AI_Medical_Report_Analysis.pdf";
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);

    } catch (err) {
        console.error("Download error:", err);
        showStatusAlert("An error occurred while generating the PDF report.", "error");
    } finally {
        if (downloadBtn) downloadBtn.disabled = false;
    }
}

// ---------------------------------------------------------------------------
// NOTIFICATIONS & UTILITY HELPERS
// ---------------------------------------------------------------------------

function showStatusAlert(message, type = "info") {
    const alertBox = document.getElementById("statusAlert");
    const textSpan = document.getElementById("statusAlertText");
    const iconSpan = document.getElementById("statusAlertIcon");

    if (!alertBox || !textSpan) return;

    alertBox.className = `status-alert ${type}`;
    textSpan.textContent = message;

    if (iconSpan) {
        if (type === "error") iconSpan.textContent = "⚠";
        else if (type === "warning") iconSpan.textContent = "⚡";
        else iconSpan.textContent = "ℹ";
    }

    alertBox.classList.remove("hidden");
}

function hideStatusAlert() {
    const alertBox = document.getElementById("statusAlert");
    if (alertBox) alertBox.classList.add("hidden");
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}