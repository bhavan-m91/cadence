"""Write the OpenAPI document used to generate the frontend's TypeScript types (`make gen-api`).

Enum schemas carry an auto-generated docstring whose text differs between Python versions; it is noise,
so it is dropped to keep the snapshot identical on every interpreter.
"""

import json
import sys
from pathlib import Path

from app.main import create_app


def normalise(spec: dict) -> dict:
    for schema in spec.get("components", {}).get("schemas", {}).values():
        if "enum" in schema:
            schema.pop("description", None)
    return spec


out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
out.write_text(json.dumps(normalise(create_app().openapi()), indent=2, sort_keys=True) + "\n")
print(f"wrote {out}")
