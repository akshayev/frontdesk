"""D-045 / D-046: client IP = N-th X-Forwarded-For entry from the right (Render: 3), else the
socket peer; CF-Connecting-IP tripwire; DEBUG diagnostic."""

import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.config import Settings
from app.security.client_ip import TRIPWIRE_MESSAGE, client_ip

PEER = "testclient"  # Starlette's TestClient socket peer
LOGGER = "frontdesk.client_ip"
CLIENT, CF_EDGE, RENDER = "8.8.4.4", "172.70.1.2", "10.28.192.255"
# Exact format observed live (commit 063a7bc): <client>, <Cloudflare edge>, <Render internal>.
OBSERVED = f"{CLIENT}, {CF_EDGE}, {RENDER}"


def _client(hops: int) -> TestClient:
    app = FastAPI()
    app.state.settings = Settings(trusted_proxy_hops=hops)

    @app.get("/ip")
    def ip(request: Request) -> dict[str, str]:
        return {"ip": client_ip(request)}

    return TestClient(app)


def _ip(hops: int, *headers: str, extra: dict[str, str] | None = None) -> str:
    sent = [("x-forwarded-for", h) for h in headers] + list((extra or {}).items())
    return _client(hops).get("/ip", headers=sent).json()["ip"]


def _messages(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == level]


# --- C-1: position from the right -------------------------------------------------------------

def test_observed_render_format_gives_the_client() -> None:
    assert _ip(3, OBSERVED) == CLIENT


def test_spoofed_prepended_entry_still_gives_the_real_client() -> None:
    assert _ip(3, f"203.0.113.7, {OBSERVED}") == CLIENT
    assert _ip(3, f"1.1.1.1, 2.2.2.2, 203.0.113.7, {OBSERVED}") == CLIENT


def test_one_hop_takes_the_rightmost_entry() -> None:
    assert _ip(1, "203.0.113.7, 198.51.100.9") == "198.51.100.9"
    assert _ip(1, "198.51.100.9") == "198.51.100.9"


def test_whitespace_is_stripped() -> None:
    assert _ip(3, f"  {CLIENT} ,{CF_EDGE} ,   {RENDER}  ") == CLIENT


def test_several_header_lines_count_as_one_list() -> None:
    assert _ip(3, f"203.0.113.7, {CLIENT}", f"{CF_EDGE}, {RENDER}") == CLIENT


# --- C-2: settings ----------------------------------------------------------------------------

def test_zero_hops_ignores_the_header_entirely() -> None:
    assert _ip(0, OBSERVED) == PEER
    assert _ip(0, "198.51.100.9") == PEER


def test_default_setting_is_zero_hops() -> None:
    assert Settings().trusted_proxy_hops == 0


def test_negative_hops_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(trusted_proxy_hops=-1)


# --- C-3: fallback and parsing ----------------------------------------------------------------

def test_missing_header_falls_back_to_the_peer() -> None:
    assert _client(3).get("/ip").json()["ip"] == PEER


def test_fewer_entries_than_hops_falls_back_with_a_debug_line(
        caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert _ip(3, f"{CF_EDGE}, {RENDER}") == PEER
    [line] = _messages(caplog, logging.DEBUG)
    assert f"fallback to peer: xff_lines=1 xff_entries=2 rightmost=' {RENDER}'" in line
    assert "kinds=global,private peer_match=True proxy_headers=x-forwarded-for" in line
    assert not _messages(caplog, logging.WARNING)


@pytest.mark.parametrize("value", ["not-an-ip", "", ",", "203.0.113.7, banana", "1.2.3.4:80",
                                   "999.1.1.1", "198.51.100.9, "])
def test_malformed_chosen_entry_falls_back_to_the_peer(value: str) -> None:
    assert _ip(1, value) == PEER


def test_ipv6_is_accepted_and_canonicalised() -> None:
    assert _ip(3, f"2001:4860:0:0::0:8888, {CF_EDGE}, {RENDER}") == "2001:4860::8888"
    assert _ip(1, "::1") == "::1"


# --- C-4: CF-Connecting-IP tripwire (D-046) ---------------------------------------------------

def test_tripwire_warns_on_mismatch_and_keeps_the_chosen_ip(
        caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert _ip(3, OBSERVED, extra={"cf-connecting-ip": "9.9.9.9"}) == CLIENT
    assert _messages(caplog, logging.WARNING) == [TRIPWIRE_MESSAGE]
    assert "9.9.9.9" not in caplog.text and CLIENT not in TRIPWIRE_MESSAGE


def test_tripwire_silent_when_cf_matches_or_is_absent(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        _ip(3, OBSERVED, extra={"cf-connecting-ip": CLIENT})
        _ip(3, OBSERVED)
        _ip(0, OBSERVED, extra={"cf-connecting-ip": "9.9.9.9"})  # hops=0: nothing to compare
    assert not _messages(caplog, logging.WARNING)


def test_tripwire_fires_when_the_chain_got_shorter(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert _ip(3, f"{CF_EDGE}, {RENDER}", extra={"cf-connecting-ip": CLIENT}) == PEER
    assert _messages(caplog, logging.WARNING) == [TRIPWIRE_MESSAGE]


# --- diagnostic (DEBUG) -----------------------------------------------------------------------

def test_diagnostic_is_debug_only_and_logs_names_not_values(
        caplog: pytest.LogCaptureFixture) -> None:
    headers = {"x-forwarded-for": "203.0.113.7, banana", "x-real-ip": "198.51.100.1",
               "x-render-origin-server": "secret-value", "cookie": "fd_session=tok123"}
    with caplog.at_level(logging.INFO, logger=LOGGER):
        _client(1).get("/ip", headers=headers)
    assert not caplog.records  # not emitted above DEBUG
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert _client(1).get("/ip", headers=headers).json()["ip"] == PEER
    [line] = _messages(caplog, logging.DEBUG)
    assert "proxy_headers=x-forwarded-for,x-real-ip,x-render-origin-server" in line
    for value in ("198.51.100.1", "secret-value", "tok123", "fd_session", "cookie"):
        assert value not in line


def test_diagnostic_truncates_the_rightmost_entry(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        _ip(1, "x" * 200)
    assert "rightmost='" + "x" * 64 + "'" in _messages(caplog, logging.DEBUG)[-1]


def test_no_diagnostic_for_a_public_chosen_entry(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        _ip(0, "banana")
        _ip(3, OBSERVED)
    assert not caplog.records
