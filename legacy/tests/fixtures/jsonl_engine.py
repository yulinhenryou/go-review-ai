"""Subprocess protocol test double; never imported by the application."""
import json
import sys
import time

mode = sys.argv[1]
for line in sys.stdin:
    query = json.loads(line)
    if mode == "timeout":
        time.sleep(30)
    if mode == "exit":
        sys.exit(2)
    if mode == "malformed":
        print("not json", flush=True)
        continue
    if mode == "nonfinite":
        print('{"value":NaN}', flush=True)
        continue
    if mode == "oversized":
        print("x" * (4 * 1024 * 1024 + 1), flush=True)
        continue
    if mode == "stderr":
        sys.stderr.write("diagnostic\n" * 20000)
        sys.stderr.flush()
    if mode == "error":
        print(json.dumps({"error": "private /path/config error"}), flush=True)
        continue
    if mode in {"warning", "rules_warning"}:
        print(json.dumps({"id": query["id"], "warning": "private /path", "field":
                          "rules" if mode == "rules_warning" else "other"}), flush=True)
    for turn in reversed(query["analyzeTurns"]):
        message = {"id": query["id"], "turnNumber": turn, "isDuringSearch": False}
        if mode == "interim":
            print(json.dumps(message | {"isDuringSearch": True}), flush=True)
        if mode == "wrong_id":
            message["id"] = "unknown"
        if mode == "wrong_turn":
            message["turnNumber"] = 999
        if mode == "bool_turn":
            message["turnNumber"] = False
        if mode == "no_final_flag":
            del message["isDuringSearch"]
        output = json.dumps(message) + "\n"
        if mode == "duplicate":
            output += output
        if mode == "fragmented":
            for chunk in (output[:5], output[5:]):
                sys.stdout.write(chunk)
                sys.stdout.flush()
        else:
            sys.stdout.write(output)
            sys.stdout.flush()
