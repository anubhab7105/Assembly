"""Export the progress-event JSON Schema for frontend type derivation.

Usage:  python scripts/export_event_schema.py [--out PATH]

Writes {"version", "event_types", "envelope", "payloads"} where each
entry is a standard JSON Schema dict (Pydantic model_json_schema).
Generate TypeScript types from it with e.g.:
  npx --yes quicktype --src-lang schema --lang ts schema.json

The committed artifact lives at frontend/event-schema.json — regenerate
it whenever src/api/events.py changes.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.api.events import event_schema_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "frontend" / "event-schema.json"),
        help="Destination JSON file.",
    )
    args = parser.parse_args()

    bundle = event_schema_bundle()
    out_path = Path(args.out)
    out_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {out_path} "
        f"({len(bundle['event_types'])} event types, "
        f"{len(bundle['payloads'])} payload models)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
