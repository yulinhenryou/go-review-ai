"""Run the Python suite with the same local KataGo discovery as the app."""
from __future__ import annotations

import os
import subprocess
import sys

from local_server import engine_environment, loaded


def main() -> int:
    if sys.platform == "darwin" and loaded():
        print(
            "Stop the local Go Review service before the live KataGo release check: "
            "python scripts/local_server.py stop",
            file=sys.stderr,
        )
        return 2
    environment = os.environ.copy()
    environment.update(engine_environment())
    environment["RUN_KATAGO_INTEGRATION"] = "1"
    return subprocess.call(
        [sys.executable, "-m", "pytest", "-q", "-ra"],
        env=environment,
    )


if __name__ == "__main__":
    raise SystemExit(main())
