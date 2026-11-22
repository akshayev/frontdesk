"""A-3 (D-045): only app/security/client_ip.py may read X-Forwarded-For or the raw peer address;
every rate-limit key and audit IP must come from client_ip()."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
ALLOWED = {APP / "security" / "client_ip.py"}
PATTERN = re.compile(r"x-forwarded|request\.client\b|get_remote_address|forwarded_allow", re.I)


def test_only_client_ip_module_reads_the_forwarded_header_or_peer() -> None:
    offenders = []
    for path in APP.rglob("*.py"):
        if path in ALLOWED:
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            if PATTERN.search(line) and not stripped.startswith(("#", '"""')):
                offenders.append(f"{path.relative_to(APP)}:{n}")
    assert not offenders, f"read the client address only through client_ip(): {offenders}"
