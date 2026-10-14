"""Tests for rate-limit retry and HTTP error messages (issue #16)."""

from __future__ import annotations

import datetime
from email.utils import format_datetime

import httpx
import pytest

from mosaic.search import search_all
from mosaic.sources.base import (
    RetryTransport,
    describe_http_error,
    http_client,
    retry_after_seconds,
)


def _scripted(*responses: httpx.Response):
    """MockTransport replaying *responses* in order; records each request."""
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0)

    return httpx.MockTransport(handler), seen


def _client(inner, sleeps, **kw) -> httpx.Client:
    return httpx.Client(transport=RetryTransport(transport=inner, sleep=sleeps.append, **kw))


class TestRetryAfterParsing:
    def test_delta_seconds(self):
        assert retry_after_seconds("7") == 7.0

    def test_http_date(self):
        when = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=30)
        secs = retry_after_seconds(format_datetime(when, usegmt=True))
        assert secs is not None and 25 <= secs <= 31

    def test_past_date_clamped_to_zero(self):
        assert retry_after_seconds("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0

    @pytest.mark.parametrize("value", [None, "", "soon"])
    def test_absent_or_garbage(self, value):
        assert retry_after_seconds(value) is None


class TestRetryTransport:
    def test_429_with_short_retry_after_is_retried(self):
        inner, seen = _scripted(
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"ok": True}),
        )
        sleeps: list[float] = []
        with _client(inner, sleeps) as c:
            r = c.get("https://api.example.org/q")
        assert r.status_code == 200
        assert len(seen) == 2
        assert sleeps == [2.0]

    def test_503_without_header_uses_exponential_backoff(self):
        inner, seen = _scripted(httpx.Response(503), httpx.Response(503), httpx.Response(200))
        sleeps: list[float] = []
        with _client(inner, sleeps) as c:
            assert c.get("https://api.example.org/q").status_code == 200
        assert sleeps == [1.0, 2.0]

    def test_long_retry_after_fails_fast(self):
        """A daily-quota style wait must not hang the search."""
        inner, seen = _scripted(httpx.Response(429, headers={"Retry-After": "3600"}))
        sleeps: list[float] = []
        with _client(inner, sleeps) as c:
            r = c.get("https://api.example.org/q")
        assert r.status_code == 429
        assert len(seen) == 1
        assert sleeps == []

    def test_gives_up_after_max_retries(self):
        inner, seen = _scripted(*[httpx.Response(429, headers={"Retry-After": "0"})] * 3)
        sleeps: list[float] = []
        with _client(inner, sleeps, max_retries=2) as c:
            assert c.get("https://api.example.org/q").status_code == 429
        assert len(seen) == 3

    @pytest.mark.parametrize("status", [200, 400, 403, 404, 500])
    def test_other_statuses_not_retried(self, status):
        inner, seen = _scripted(httpx.Response(status))
        with _client(inner, []) as c:
            assert c.get("https://api.example.org/q").status_code == status
        assert len(seen) == 1

    def test_post_body_resent_on_retry(self):
        inner, seen = _scripted(
            httpx.Response(429, headers={"Retry-After": "0"}), httpx.Response(200)
        )
        with _client(inner, []) as c:
            c.post("https://api.example.org/q", data={"id": "1,2"})
        assert [r.content for r in seen] == [b"id=1%2C2", b"id=1%2C2"]

    def test_http_client_factory_installs_retry(self):
        with http_client(timeout=5) as c:
            assert isinstance(c._transport, RetryTransport)


def _status_error(status: int, body: str = "", headers: dict | None = None):
    req = httpx.Request("GET", "https://ieeexploreapi.ieee.org/api/v1/search")
    resp = httpx.Response(status, text=body, headers=headers or {}, request=req)
    return httpx.HTTPStatusError("boom", request=req, response=resp)


class TestDescribeHttpError:
    def test_429_with_retry_after(self):
        msg = describe_http_error(_status_error(429, headers={"Retry-After": "120"}))
        assert msg == "rate limited (HTTP 429); retry in ~120s"

    def test_429_without_retry_after(self):
        assert "try again later" in describe_http_error(_status_error(429))

    def test_ieee_daily_quota_403(self):
        msg = describe_http_error(_status_error(403, "<h1>Developer Over Rate</h1>"))
        assert msg.startswith("API quota exhausted (HTTP 403)")

    def test_plain_403_points_to_credentials(self):
        msg = describe_http_error(_status_error(403, "Forbidden"))
        assert "check the API key" in msg

    def test_other_status_names_host(self):
        assert describe_http_error(_status_error(500)) == "HTTP 500 from ieeexploreapi.ieee.org"

    def test_timeout(self):
        assert describe_http_error(httpx.ReadTimeout("slow")) == "timed out"

    def test_non_http_error_passthrough(self):
        assert describe_http_error(RuntimeError("parse failure")) == "parse failure"


class TestSearchAllReportsQuota:
    def test_quota_error_is_readable_in_errors(self):
        from unittest.mock import MagicMock

        from mosaic.sources.base import BaseSource

        src = MagicMock(spec=BaseSource)
        src.name = "IEEE"
        src.available.return_value = True
        src.search.side_effect = _status_error(403, "Developer Over Rate")
        errors: list[str] = []
        search_all([src], "q", errors=errors)
        assert errors == ["IEEE: API quota exhausted (HTTP 403); try again later or tomorrow"]
