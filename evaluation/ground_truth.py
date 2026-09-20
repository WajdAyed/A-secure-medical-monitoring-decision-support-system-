"""Clinician-reviewable reference labels; never sent to a service."""
import json
from .config import ROOT
from device_agent.sensor import evaluation_sensor_value

REFERENCE_PATH = ROOT / "evaluation" / "reference_ranges.json"
_FALLBACKS = {"hypertension":("systolic_bp",110,135),"diabetes":("blood_glucose",70,140),"asthma":("peak_flow_percent",80,100),"heart_failure":("weight_kg",60,90),"copd":("oxygen_saturation",92,100),"renal_failure":("creatinine",1,2),"obesity":("bmi",18,30),"anemia":("hemoglobin",12,16),"arrhythmia":("heart_rate",60,100),"stroke_risk":("systolic_bp",110,135),"depression":("sleep_hours",7,9),"arthritis":("pain_score",0,4)}
_PDFS={"diabetes":"Diabetes guideline.pdf","hypertension":"Hypertension guideline.pdf","heart_failure":"Heart Failure guideline.pdf"}
def ensure_reference_ranges():
    ranges={c:{"parameter":p,"min":lo,"max":hi,"source_pdf":_PDFS.get(c,"No condition-specific PDF in RAG/guidelines"),"page":None,"section":"TO BE VERIFIED BY CLINICIAN/SUPERVISOR"} for c,(p,lo,hi) in _FALLBACKS.items()}
    REFERENCE_PATH.write_text(json.dumps({"status":"TO BE VERIFIED BY CLINICIAN/SUPERVISOR","method":"Project documented fallback ranges; only three conditions have local guideline PDFs.","ranges":ranges},indent=2),encoding="utf-8")
    return ranges
def stable(patient_id, condition):
    ref = ensure_reference_ranges().get(condition)
    return None if ref is None else ref["min"] <= evaluation_sensor_value(patient_id) <= ref["max"]
