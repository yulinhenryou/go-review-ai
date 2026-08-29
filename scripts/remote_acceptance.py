"""M5 real-service acceptance using only the checked-in public sample."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

EXPECTED_MODEL_SHA256 = "9d7a6afed8ff5b74894727e156f04f0cd36060a24824892008fbb6e0cba51f1d"
EXPECTED_MISTAKE_REGION = {1, 3, 5}
SAMPLE = Path("samples/m3_mistake.sgf")


def request_json(base_url, path, *, method="GET", body=None, content_type=None, timeout=30):
    headers = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(
        base_url.rstrip("/") + path, data=body, headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc


def parse_upload(base_url):
    boundary = "go-review-" + uuid.uuid4().hex
    sample = SAMPLE.read_bytes()
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="m3_mistake.sgf"\r\n'
        "Content-Type: application/x-go-sgf\r\n\r\n"
    ).encode() + sample + f"\r\n--{boundary}--\r\n".encode()
    return request_json(
        base_url, "/api/v1/parse-sgf", method="POST", body=body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )


def submit_and_wait(base_url, game, warnings=()):
    payload = {
        **game,
        "loss_threshold": 3.0,
        "severe_threshold": 5.0,
        "limit": 5,
        "input_warnings": list(warnings),
    }
    payload.pop("record_status", None)
    job = request_json(
        base_url, "/api/v1/jobs", method="POST",
        body=json.dumps(payload, allow_nan=False).encode(), content_type="application/json",
    )
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        job = request_json(base_url, f"/api/v1/jobs/{job['id']}")
        if job["state"] == "succeeded":
            return job["result"]
        if job["state"] in {"failed", "cancelled"}:
            raise RuntimeError(f"Analysis ended in {job['state']}: {job.get('error')}")
        time.sleep(2)
    raise RuntimeError("Analysis did not finish within 900 seconds")


def validate_report(report):
    assert report["schema_version"] == "3.0"
    assert report["engine_source"] == "katago"
    assert report["status"] == "complete"
    assert report["coverage"]["moves_total"] == 6
    assert report["coverage"]["moves_evaluated"] == 6
    evidence = report["timeline"][0]["evidence"]
    assert evidence["model_sha256"] == EXPECTED_MODEL_SHA256
    assert evidence["max_visits"] == 64

    traceable = []
    for mistake in report["selected_mistakes"]:
        recommended = mistake["recommended_move"]["sgf"]
        candidates = {candidate["move"]["sgf"] for candidate in mistake["top_candidates"]}
        if (mistake["move_number"] in EXPECTED_MISTAKE_REGION
                and mistake["score_loss"] >= 5.0 and recommended in candidates):
            traceable.append(mistake)
    assert traceable, "Expected a >=5 point engine-backed loss around moves 1, 3 or 5"
    return evidence, traceable


def summary(report):
    return [{
        "move_number": item["move_number"],
        "played_sgf": item["played_move"]["sgf"],
        "recommended_sgf": item["recommended_move"]["sgf"],
        "score_loss": item["score_loss"],
    } for item in report["selected_mistakes"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", help="Public HTTPS origin or local container origin")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    release = request_json(args.base_url, "/release")
    assert request_json(args.base_url, "/health") == {"status": "ok"}
    ready = request_json(args.base_url, "/ready", timeout=120)
    assert ready["status"] == "ready"
    assert ready["model_sha256"] == EXPECTED_MODEL_SHA256

    preview = parse_upload(args.base_url)
    assert preview["status"] == "ready"
    uploaded = submit_and_wait(args.base_url, preview["game"], preview["warnings"])

    manual_game = {
        "board_size": 19,
        "rules": "chinese",
        "komi": 7.5,
        "players": {"black": "M5 manual black", "white": "M5 manual white"},
        "result": None,
        "moves": [
            {"color": "B", "sgf": "aa"}, {"color": "W", "sgf": "pp"},
            {"color": "B", "sgf": "ba"}, {"color": "W", "sgf": "dd"},
            {"color": "B", "sgf": "ca"}, {"color": "W", "sgf": "dp"},
        ],
    }
    manual = submit_and_wait(args.base_url, manual_game)
    uploaded_evidence, uploaded_traceable = validate_report(uploaded)
    manual_evidence, manual_traceable = validate_report(manual)

    result = {
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "origin": args.base_url,
        "release": release,
        "engine": {
            "version": uploaded_evidence["engine_version"],
            "model_id": uploaded_evidence["model_id"],
            "model_sha256": uploaded_evidence["model_sha256"],
            "config_sha256": uploaded_evidence["config_sha256"],
            "max_visits": uploaded_evidence["max_visits"],
        },
        "input": {
            "sample": str(SAMPLE),
            "sgf_sha256": hashlib.sha256(SAMPLE.read_bytes()).hexdigest(),
            "moves": 6,
            "rules": "chinese",
            "komi": 7.5,
        },
        "uploaded": {"selected_mistakes": summary(uploaded),
                     "traceable_region": [item["move_number"] for item in uploaded_traceable]},
        "manual": {"selected_mistakes": summary(manual),
                   "traceable_region": [item["move_number"] for item in manual_traceable]},
        "same_engine": all(uploaded_evidence[key] == manual_evidence[key] for key in (
            "engine_version", "model_id", "model_sha256", "config_sha256", "max_visits",
        )),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
