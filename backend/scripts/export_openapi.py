"""Write the OpenAPI document used to generate the frontend's TypeScript types (`make gen-api`)."""

import json
import sys
from pathlib import Path

from app.main import create_app

out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
out.write_text(json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n")
print(f"wrote {out}")
