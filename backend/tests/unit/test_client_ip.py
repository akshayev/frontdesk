"""D-045: client IP = rightmost X-Forwarded-For entry behind one trusted proxy, else the peer."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.config import Settings
from app.security.client_ip import client_ip

PEER = "testclient"  # Starlette's TestClient socket peer


def _client(hops: int) -> TestClient:
    app = FastAPI()
    app.state.settings = Settings(trusted_proxy_hops=hops)

    @app.get("/ip")
    def ip(request: Request) -> dict[str, str]:
        return {"ip": client_ip(request)}

    return TestClient(app)


def _ip(hops: int, *headers: str) -> str:
    return _client(hops).get("/ip", headers=[("x-forwarded-for", h) for h in headers]).json()["ip"]


def test_spoofed_leftmost_values_are_ignored_with_one_hop() -> None:
    assert _ip(1, "203.0.113.7, 198.51.100.9") == "198.51.100.9"
    assert _ip(1, "1.1.1.1, 2.2.2.2, 3.3.3.3, 198.51.100.9") == "198.51.100.9"


def test_single_entry_is_the_client() -> None:
    assert _ip(1, "198.51.100.9") == "198.51.100.9"


def test_whitespace_is_stripped() -> None:
    assert _ip(1, "203.0.113.7 ,   198.51.100.9  ") == "198.51.100.9"


def test_zero_hops_ignores_the_header_entirely() -> None:
    assert _ip(0, "198.51.100.9") == PEER
    assert _ip(0, "203.0.113.7, 198.51.100.9") == PEER


def test_default_setting_is_zero_hops() -> None:
    assert Settings().trusted_proxy_hops == 0


def test_missing_header_falls_back_to_the_peer() -> None:
    assert _client(1).get("/ip").json()["ip"] == PEER


@pytest.mark.parametrize("value", ["not-an-ip", "", ",", "203.0.113.7, banana", "1.2.3.4:80",
                                   "999.1.1.1", "198.51.100.9, "])
def test_malformed_rightmost_entry_falls_back_to_the_peer(value: str) -> None:
    assert _ip(1, value) == PEER


def test_ipv6_is_accepted_and_canonicalised() -> None:
    assert _ip(1, "203.0.113.7, 2001:DB8::0:1") == "2001:db8::1"
    assert _ip(1, "::1") == "::1"


def test_several_header_lines_count_as_one_list() -> None:
    assert _ip(1, "203.0.113.7", "198.51.100.9") == "198.51.100.9"


def test_two_hops_takes_the_second_entry_from_the_right() -> None:
    assert _ip(2, "203.0.113.7, 198.51.100.9, 10.0.0.1") == "198.51.100.9"
    assert _ip(2, "198.51.100.9") == PEER  # fewer entries than trusted hops → malformed


def test_negative_hops_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(trusted_proxy_hops=-1)
