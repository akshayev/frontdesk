"""CSV exports with a formula-injection guard. Implements: RPT-2, SECURITY §6.

A spreadsheet treats a cell starting with = + - @ (or tab / carriage return) as a formula, so a
customer could put `=HYPERLINK(...)` in a subject. Such cells are prefixed with `'`, which
spreadsheets show as plain text (OWASP "CSV injection").
"""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from fastapi.responses import Response

from app.sla.calendar import TZ

# Route options for a CSV endpoint: the OpenAPI schema declares text/csv (not JSON), so the
# generated frontend types match what the server really sends.
CSV_ROUTE: dict[str, Any] = {
    "response_class": Response,
    "responses": {200: {"description": "CSV attachment (UTF-8, formula-guarded cells).",
                        "content": {"text/csv": {"schema": {"type": "string"}}}}},
}

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> str:
    """The cell text, prefixed with ' when a spreadsheet would read it as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def ist(value: datetime | None) -> str:
    """AUD-4: exact time to the second, in IST (e.g. 2026-11-23T10:00:05+05:30)."""
    return "" if value is None else value.astimezone(TZ).isoformat(timespec="seconds")


def csv_response(filename: str, header: Sequence[str],
                 rows: Iterable[Sequence[object]]) -> Response:
    """A text/csv attachment; every cell (header included) goes through safe_cell."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([safe_cell(h) for h in header])
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return Response(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
