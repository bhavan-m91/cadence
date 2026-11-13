"""Write the OpenAPI document used to generate the frontend's TypeScript types (`make gen-api`).

Two strings come from the Python standard library and differ between versions, so the snapshot is
normalised to stay identical on every interpreter: enum docstrings (3.12 adds one, 3.13 does not) and
the HTTP 422 reason phrase ("Unprocessable Entity" in 3.12, "Unprocessable Content" in 3.13).
"""

import json
import sys
from pathlib import Path

from app.main import create_app


def normalise(spec: dict) -> dict:
    for schema in spec.get("components", {}).get("schemas", {}).values():
        if "enum" in schema:
            schema.pop("description", None)
    for methods in spec.get("paths", {}).values():
        for op in methods.values():
            if isinstance(op, dict) and "422" in op.get("responses", {}):
                op["responses"]["422"]["description"] = "Validation Error"
    return spec


out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
out.write_text(json.dumps(normalise(create_app().openapi()), indent=2, sort_keys=True) + "\n")
print(f"wrote {out}")
