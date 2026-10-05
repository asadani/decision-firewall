"""Fresh-process simulated recovery worker for the pilot."""

import json
import sys

from .adapters import Bridge

if __name__ == "__main__":
    target = Bridge(
        sys.argv[1],
        "lost_response",
        sys.argv[2],
        None if sys.argv[3] == "none" else sys.argv[3],
        resume=True,
    )
    print(json.dumps({"status": target.engine.reconcile(target.handle)}))
