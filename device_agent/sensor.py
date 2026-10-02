import random
import hashlib


def read_heart_rate():
    return random.randint(55, 110)


def read_systolic_bp():
    return random.randint(100, 170)


def read_spo2():
    return random.randint(90, 100)


def read_temperature():
    return round(random.uniform(36.0, 41.0), 1)


def read_measurement(parameter: str):
    readers = {
        "systolic_bp": read_systolic_bp,
        "heart_rate": read_heart_rate,
        "oxygen_saturation": read_spo2,
        "temperature": read_temperature,
        "sleep_hours": lambda: random.randint(5, 10),
        "blood_glucose": lambda: random.randint(50, 220),
        "peak_flow_percent": lambda: random.randint(50, 120),
        "weight_kg": lambda: random.randint(40, 140),
        "creatinine": lambda: random.randint(0, 5),
        "bmi": lambda: random.randint(15, 40),
        "hemoglobin": lambda: random.randint(8, 20),
        "pain_score": lambda: random.randint(0, 10),
    }
    try:
        return readers[parameter.lower()]()
    except KeyError as exc:
        raise ValueError(f"Unsupported sensor parameter: {parameter}") from exc


def evaluation_sensor_value(patient_id: str, parameter: str = "systolic_bp") -> int:
    """Deterministic, local-only value for CDSS_EVAL ground truth.

    This function deliberately does not publish values through HTTP or logs.
    """
    digest = hashlib.sha256(f"cdss-eval-42:{parameter}:{patient_id}".encode()).digest()
    ranges = {
        "systolic_bp": (60, 200),
        "heart_rate": (40, 140),
        "oxygen_saturation": (80, 100),
        "sleep_hours": (4, 12),
        "blood_glucose": (40, 250),
        "peak_flow_percent": (40, 120),
        "weight_kg": (40, 140),
        "creatinine": (0, 5),
        "bmi": (15, 40),
        "hemoglobin": (8, 20),
        "pain_score": (0, 10),
    }
    lower, upper = ranges.get(parameter.lower(), (0, 200))
    return lower + int.from_bytes(digest[:2], "big") % (upper - lower + 1)
