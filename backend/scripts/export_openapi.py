"""Write the app's OpenAPI schema (the frontend's API contract, D-037) to stdout.

`uv run python -m scripts.export_openapi > ../frontend/openapi.json`. Builds the app without a
database connection (the engine is created lazily and never used here). Output is stable
(indented, keys in FastAPI's order) so `npm run check:api` can diff it.
"""

import json
import sys

from app.config import Settings
from app.main import create_app


def main() -> None:
    """Print the schema. Settings come from defaults only, never from .env secrets."""
    app = create_app(Settings(_env_file=None, sweep_enabled=False))  # type: ignore[call-arg]
    json.dump(app.openapi(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
