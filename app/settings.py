import json
import os
import re
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


def public_options():
    if os.environ.get("GO_REVIEW_PUBLIC") != "1":
        raise ValueError("Set GO_REVIEW_PUBLIC=1 to start the public service")

    fly_app = os.environ.get("FLY_APP_NAME", "").strip().lower()
    default_hosts = json.dumps([f"{fly_app}.fly.dev"]) if fly_app else "[]"
    hosts = json.loads(os.environ.get("GO_REVIEW_PUBLIC_HOSTS", default_hosts))
    if not isinstance(hosts, list) or not hosts:
        raise ValueError("GO_REVIEW_PUBLIC_HOSTS must be a non-empty JSON list")
    for host in hosts:
        if (not isinstance(host, str) or host != host.strip().lower()
                or not re.fullmatch(r"[a-z0-9.:-]+", host)):
            raise ValueError("Public hosts must be exact lowercase Host header values")

    release = os.environ.get("GO_REVIEW_RELEASE", "unreleased")
    if release != "unreleased" and not re.fullmatch(r"[0-9a-f]{40}", release):
        raise ValueError("GO_REVIEW_RELEASE must be a full lowercase Git commit hash")
    if fly_app and release == "unreleased":
        raise ValueError("Fly deployments require GO_REVIEW_RELEASE to identify the source commit")

    proxy_header = os.environ.get("GO_REVIEW_CLIENT_IP_HEADER") or None
    if proxy_header not in {None, "fly-client-ip"}:
        raise ValueError("Only Fly-Client-IP is trusted as a public client address header")

    return {
        "hosts": tuple(hosts),
        "release": release,
        "client_ip_header": proxy_header,
        "rate_window": int(os.environ.get("GO_REVIEW_RATE_WINDOW", "3600")),
        "client_limit": int(os.environ.get("GO_REVIEW_CLIENT_LIMIT", "4")),
        "global_limit": int(os.environ.get("GO_REVIEW_GLOBAL_LIMIT", "20")),
    }
