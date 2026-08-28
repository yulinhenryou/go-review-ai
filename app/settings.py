import json
import os
from urllib.parse import urlsplit


def allowed_origins():
    values = json.loads(os.environ.get("GO_REVIEW_ALLOWED_ORIGINS", '["http://localhost:3000"]'))
    if not isinstance(values, list):
        raise ValueError("GO_REVIEW_ALLOWED_ORIGINS must be a JSON list of exact origins")
    for value in values:
        if not isinstance(value, str):
            raise ValueError("CORS origins must be strings")
        url = urlsplit(value)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        secure = url.scheme == "https" or (local and url.scheme == "http")
        invalid_characters = any(ord(char) < 33 or char in "*\\?#" for char in value)
        if (not secure or not url.hostname or url.username or url.password
                or url.path or url.query or url.fragment or invalid_characters or url.port == 0):
            raise ValueError("CORS requires exact HTTPS origins or loopback HTTP origins")
    return values


def job_options():
    return {"queue_capacity": int(os.environ.get("GO_REVIEW_QUEUE_CAPACITY", "2")),
            "timeout": float(os.environ.get("GO_REVIEW_JOB_TIMEOUT", "900")),
            "retention": float(os.environ.get("GO_REVIEW_RESULT_TTL", "1800"))}
