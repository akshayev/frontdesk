"""scripts/export_openapi.py: valid JSON schema on stdout, no database needed (D-037)."""

import json

import pytest

from scripts import export_openapi


def test_export_writes_the_openapi_schema(capsys: pytest.CaptureFixture[str]) -> None:
    export_openapi.main()
    schema = json.loads(capsys.readouterr().out)
    assert schema["openapi"].startswith("3.")
    assert {"/api/agent/tickets", "/api/lead/agents", "/api/customer/ticket",
            "/api/public/tickets", "/healthz"} <= set(schema["paths"])
