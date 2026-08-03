"""Tests for serving the dashboard under a reverse-proxy sub-path.

A proxy that mounts this app below the origin root (e.g. at
"/apps/hevy2garmin") can rewrite root-absolute references in the HTML it
forwards — href, src, action, hx-* — but it cannot rewrite URLs that the
page's JavaScript builds at runtime. Those are rendered against
``window.APP_PREFIX``, which carries the X-Forwarded-Prefix value. With no
such header (a normal root install) the prefix must be empty so the emitted
URLs are unchanged.
"""

from __future__ import annotations

import os
import re

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """Client with the header explicitly trusted — the deployed-behind-a-proxy case."""
    os.environ.pop("HEVY2GARMIN_SECRET", None)
    os.environ.pop("DEMO_MODE", None)
    monkeypatch.setenv("H2G_TRUST_FORWARDED_PREFIX", "1")
    from hevy2garmin.server import app

    yield TestClient(app, follow_redirects=False)


@pytest.fixture
def untrusting_client():
    """Client with the flag absent — the default, and every non-proxied install."""
    os.environ.pop("HEVY2GARMIN_SECRET", None)
    os.environ.pop("DEMO_MODE", None)
    os.environ.pop("H2G_TRUST_FORWARDED_PREFIX", None)
    from hevy2garmin.server import app

    yield TestClient(app, follow_redirects=False)


def _app_prefix(html: str) -> str:
    m = re.search(r"window\.APP_PREFIX = (.*?);", html)
    assert m, "window.APP_PREFIX global not rendered"
    return m.group(1)


class TestReverseProxyPrefix:
    def test_prefix_injected_from_forwarded_header(self, client):
        """X-Forwarded-Prefix reaches the page, with the trailing slash trimmed."""
        resp = client.get("/setup", headers={"X-Forwarded-Prefix": "/apps/hevy2garmin/"})
        assert resp.status_code == 200
        assert _app_prefix(resp.text) == '"/apps/hevy2garmin"'

    def test_prefix_empty_without_header(self, client):
        """A root install is unaffected: the prefix is an empty string."""
        resp = client.get("/setup")
        assert resp.status_code == 200
        assert _app_prefix(resp.text) == '""'

    def test_prefix_does_not_leak_between_requests(self, client):
        """The prefix is per-request state, not sticky across requests."""
        client.get("/setup", headers={"X-Forwarded-Prefix": "/apps/hevy2garmin"})
        resp = client.get("/setup")
        assert _app_prefix(resp.text) == '""'

    def test_prefix_is_json_escaped(self, client):
        """The header is attacker-controllable, so it must be escaped, not interpolated."""
        resp = client.get("/setup", headers={"X-Forwarded-Prefix": '/x"</script><script>x'})
        assert "</script><script>x" not in _app_prefix(resp.text)

    def test_client_side_urls_are_prefixed(self, client):
        """Every JS-built URL on the page resolves under the sub-path.

        Not just fetch(): a bare `const url = '/api/…'` or a
        `location.href = '/'` escapes the prefix just as thoroughly, and those
        are the forms the direct-login POSTs and the post-connect redirect used.
        """
        resp = client.get("/setup", headers={"X-Forwarded-Prefix": "/apps/hevy2garmin"})
        assert "window.APP_PREFIX + '/api/garmin-ticket'" in resp.text
        for pattern in (
            r"fetch\((['\"])/(?!/)",            # fetch('/…')
            r"=\s*(['\"])/api/(?!/)",           # const url = '/api/…'
            r"location\.href\s*=\s*(['\"])/",  # location.href = '/…'
        ):
            assert not re.search(pattern, resp.text), pattern

    def test_direct_login_posts_are_prefixed(self, client):
        """H2G_DIRECT_GARMIN_LOGIN is exactly the self-hosted sub-path case."""
        resp = client.get("/setup", headers={"X-Forwarded-Prefix": "/apps/hevy2garmin"})
        assert "window.APP_PREFIX + '/api/garmin-login'" in resp.text
        assert "window.APP_PREFIX + '/api/garmin-login-mfa'" in resp.text

    def test_post_connect_redirect_is_prefixed(self, client):
        """Fires on every successful Garmin connect; bounced sub-path users home."""
        resp = client.get("/setup", headers={"X-Forwarded-Prefix": "/apps/hevy2garmin"})
        assert "window.location.href = (window.APP_PREFIX || '') + '/'" in resp.text


class TestServerRenderedUrlsArePrefixed:
    """Root-absolute href/src/action/hx-* must move onto the prefix too.

    The JS globals alone are not enough: an ordinary nginx/Caddy/Traefik
    sub-path mount forwards the HTML untouched, so navigation, static assets
    and every htmx call would still resolve against the origin root. The app
    is the only component that can fix all three kinds of URL, so it owns all
    three.
    """

    PREFIX = "/apps/hevy2garmin"

    def test_no_root_absolute_attribute_survives(self, client):
        resp = client.get("/setup", headers={"X-Forwarded-Prefix": self.PREFIX})
        assert resp.status_code == 200
        leftovers = re.findall(
            r'\s(?:href|src|action|hx-get|hx-post|hx-put|hx-patch|hx-delete)="/(?!/)[^"]*',
            resp.text,
        )
        assert [x for x in leftovers if self.PREFIX not in x] == []

    def test_navigation_and_assets_are_prefixed(self, client):
        resp = client.get("/setup", headers={"X-Forwarded-Prefix": self.PREFIX})
        assert f'src="{self.PREFIX}/static/favicon.svg"' in resp.text
        assert f'action="{self.PREFIX}/setup"' in resp.text

    def test_external_urls_are_untouched(self, client):
        resp = client.get("/setup", headers={"X-Forwarded-Prefix": self.PREFIX})
        assert 'href="https://fonts.googleapis.com' in resp.text
        assert f"{self.PREFIX}/https:" not in resp.text

    def test_protocol_relative_urls_are_untouched(self, client):
        from hevy2garmin.server import _apply_prefix

        assert _apply_prefix(' src="//cdn.example.com/x.js"', "/p") == ' src="//cdn.example.com/x.js"'

    def test_rewrite_is_idempotent(self, client):
        """A proxy may already have rewritten the HTML — don't prefix twice."""
        from hevy2garmin.server import _apply_prefix

        once = _apply_prefix(' href="/workouts" action="/login"', "/p")
        assert once == ' href="/p/workouts" action="/p/login"'
        assert _apply_prefix(once, "/p") == once

    def test_prefix_root_link_is_not_doubled(self):
        from hevy2garmin.server import _apply_prefix

        assert _apply_prefix(' href="/p"', "/p") == ' href="/p"'
        assert _apply_prefix(' href="/p?x=1"', "/p") == ' href="/p?x=1"'

    def test_root_install_html_is_byte_identical(self, client):
        """No header must mean no rewriting at all, not merely equivalent output."""
        plain = client.get("/setup").text
        from hevy2garmin.server import _apply_prefix

        assert _apply_prefix(plain, "") == plain
        assert 'action="/setup"' in plain


class TestRedirectLocationIsPrefixed:
    """A root-relative Location escapes the sub-path unless the app fixes it.

    nginx's proxy_redirect only rewrites absolute upstream URLs, so
    ``Location: /setup`` from the not-configured gate would send the browser to
    the origin root. These redirects come from the outer middleware, which is
    why the Location fix has to sit outside the gate that issues them.
    """

    PREFIX = "/apps/hevy2garmin"

    def test_setup_gate_redirect_is_prefixed(self, client, monkeypatch):
        monkeypatch.setattr("hevy2garmin.server._is_configured_cache", False)
        monkeypatch.setattr("hevy2garmin.server.is_configured", lambda: False)
        resp = client.get("/", headers={"X-Forwarded-Prefix": self.PREFIX})
        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == f"{self.PREFIX}/setup"

    def test_redirect_is_unchanged_at_the_root(self, client, monkeypatch):
        monkeypatch.setattr("hevy2garmin.server._is_configured_cache", False)
        monkeypatch.setattr("hevy2garmin.server.is_configured", lambda: False)
        resp = client.get("/")
        assert resp.headers["location"] == "/setup"

    def test_location_helper_is_idempotent_and_safe(self):
        from hevy2garmin.server import _prefix_location

        assert _prefix_location("/setup", "/p") == "/p/setup"
        assert _prefix_location("/p/setup", "/p") == "/p/setup"
        assert _prefix_location("/p", "/p") == "/p"
        assert _prefix_location("//evil.example.com", "/p") == "//evil.example.com"
        assert _prefix_location("https://x.example.com/y", "/p") == "https://x.example.com/y"
        assert _prefix_location("/setup", "") == "/setup"


class TestForwardedPrefixIsNotTrustedBlindly:
    """X-Forwarded-Prefix is client-supplied, and every URL on the page derives
    from it — the login form's action, the Garmin token POST, redirect targets.
    So it is read only when the operator says a proxy sets it, and then only if
    it is a plain absolute path. Both halves matter: the gate protects instances
    that are not behind a rewriting proxy at all (non-standard headers pass
    straight through hosted platforms), and the validation protects the ones that
    are, against a proxy that forwards client headers untouched.
    """

    XSS = '"><script>alert(document.domain)</script><x y="'
    OFFSITE = "//evil.example.com"

    def test_header_is_ignored_without_the_opt_in(self, untrusting_client):
        resp = untrusting_client.get(
            "/setup", headers={"X-Forwarded-Prefix": "/apps/hevy2garmin"}
        )
        assert _app_prefix(resp.text) == '""'
        assert 'action="/setup"' in resp.text

    def test_no_html_injection_through_the_prefix(self, client):
        resp = client.get("/setup", headers={"X-Forwarded-Prefix": self.XSS})
        assert "<script>alert(document.domain)</script>" not in resp.text
        assert _app_prefix(resp.text) == '""'

    def test_protocol_relative_prefix_cannot_repoint_urls(self, client):
        """//evil.example.com would send the password and Garmin tokens off-site."""
        resp = client.get("/setup", headers={"X-Forwarded-Prefix": self.OFFSITE})
        assert "evil.example.com" not in resp.text
        assert _app_prefix(resp.text) == '""'
        assert 'action="/setup"' in resp.text

    @pytest.mark.parametrize(
        "bad",
        [
            '"><script>x</script>',
            "//evil.example.com",
            "///evil.example.com",
            "https://evil.example.com",
            "javascript:alert(1)",
            "/a'b",
            "/a<b>",
            "/a b",
            "/a\\\\b",
            "no-leading-slash",
            "/",
            "",
            "/a%2e%2e",
            "/a?b=c",
            "/a#b",
        ],
    )
    def test_rejected_shapes_fall_back_to_the_root(self, bad):
        from hevy2garmin.server import _validated_prefix

        assert _validated_prefix(bad) == "", bad

    @pytest.mark.parametrize(
        "good,expected",
        [
            ("/hevy2garmin", "/hevy2garmin"),
            ("/apps/hevy2garmin", "/apps/hevy2garmin"),
            ("/apps/hevy2garmin/", "/apps/hevy2garmin"),
            ("/a-b_c.d~e", "/a-b_c.d~e"),
        ],
    )
    def test_accepted_shapes_survive(self, good, expected):
        from hevy2garmin.server import _validated_prefix

        assert _validated_prefix(good) == expected

    def test_redirect_cannot_be_sent_off_site(self):
        from hevy2garmin.server import _prefix_location

        assert _prefix_location("/login", "//evil.example.com") == "/login"
        assert _prefix_location("/login", "/apps/h2g") == "/apps/h2g/login"

    def test_html_sink_escapes_even_if_validation_were_bypassed(self):
        """Defense in depth: the sink must hold on its own."""
        from hevy2garmin.server import _apply_prefix

        out = _apply_prefix(' href="/workouts"', '"><script>x</script>')
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_opt_in_accepts_the_documented_flag_spellings(self, monkeypatch):
        from hevy2garmin.server import trust_forwarded_prefix

        for on in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv("H2G_TRUST_FORWARDED_PREFIX", on)
            assert trust_forwarded_prefix() is True, on
        for off in ("", "0", "false", "no", "off", "maybe"):
            monkeypatch.setenv("H2G_TRUST_FORWARDED_PREFIX", off)
            assert trust_forwarded_prefix() is False, off
