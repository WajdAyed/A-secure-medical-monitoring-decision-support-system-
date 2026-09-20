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


def evaluation_sensor_value(patient_id: str) -> int:
    """Deterministic, local-only systolic value for CDSS_EVAL ground truth.

    This function deliberately does not publish values through HTTP or logs.
    """
    digest = hashlib.sha256(f"cdss-eval-42:{patient_id}".encode()).digest()
    return 60 + int.from_bytes(digest[:2], "big") % 141
