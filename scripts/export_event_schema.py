"""Export the progress-event JSON Schema for frontend type derivation.

Usage:  python scripts/export_event_schema.py [--out PATH] [--check]

Writes {"version", "event_types", "envelope", "payloads"} where each
entry is a standard JSON Schema dict (Pydantic model_json_schema).
Generate TypeScript types from it with e.g.:
  npx --yes quicktype --src-lang schema --lang ts schema.json

The committed artifact lives at frontend/event-schema.json — regenerate
it whenever src/api/events.py changes.
"""

import argparse
import difflib
import json
import shlex
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
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the destination differs from the generated schema; never write it.",
    )
    args = parser.parse_args()

    bundle = event_schema_bundle()
    out_path = Path(args.out)
    rendered = json.dumps(bundle, indent=2) + "\n"
    if args.check:
        command = (
            f"python scripts/export_event_schema.py --out {shlex.quote(str(out_path))}"
        )
        try:
            current = out_path.read_bytes()
        except OSError as error:
            print(
                f"Cannot read {out_path}: {error}. Regenerate with:\n{command}",
                file=sys.stderr,
            )
            return 1
        # Git may check out the committed artifact with CRLF on Windows.
        # Ignore that transport-only difference without rewriting the file.
        normalized = current.replace(b"\r\n", b"\n")
        if normalized != rendered.encode("utf-8"):
            print(
                f"Schema artifact {out_path} is out of date. Regenerate with:\n{command}",
                file=sys.stderr,
            )
            diff = difflib.unified_diff(
                normalized.decode("utf-8", errors="replace").splitlines(keepends=True),
                rendered.splitlines(keepends=True),
                fromfile=str(out_path),
                tofile="generated event schema",
            )
            sys.stderr.writelines(diff)
            return 1
        print(f"Schema artifact {out_path} is up to date.")
        return 0
    out_path.write_bytes(rendered.encode("utf-8"))
    print(
        f"Wrote {out_path} "
        f"({len(bundle['event_types'])} event types, "
        f"{len(bundle['payloads'])} payload models)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
