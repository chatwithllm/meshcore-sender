"""Authenticated async client; credentials and session never enter entity state."""

import asyncio
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

import aiohttp


class MeshCoreError(Exception):
    """The server could not complete a request."""


class MeshCoreAuthError(MeshCoreError):
    """Authentication requires user attention."""


def normalize_url(value):
    """Require an explicit HTTP endpoint without embedded credentials."""
    url = value.strip().rstrip("/")
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        raise ValueError("Use the server URL, e.g. http://homeassistant.local:8788")
    return url


class MeshCoreClient:
    def __init__(self, session, url, passphrase):
        self.session = session
        self.url = normalize_url(url)
        self.passphrase = passphrase
        self._cookie = None
        self._csrf = None
        self._auth_lock = asyncio.Lock()

    async def _request(self, method, path, payload=None):
        headers = {}
        if self._cookie:
            headers["Cookie"] = "ms_session=" + self._cookie
        if method == "POST" and self._csrf:
            headers["X-CSRF-Token"] = self._csrf
        try:
            async with self.session.request(
                method, self.url + path, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=90), allow_redirects=False,
            ) as response:
                data = await response.json()
                if not isinstance(data, dict):
                    raise MeshCoreError("MeshCore server returned invalid data")
                return response.status, data, response.headers.get("Set-Cookie", "")
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
            raise MeshCoreError("MeshCore server is unavailable or returned invalid data") from error

    async def login(self):
        async with self._auth_lock:
            status, data, cookie_header = await self._request(
                "POST", "/api/login", {"passphrase": self.passphrase}
            )
            if status in (401, 428):
                raise MeshCoreAuthError("Set up the server or check its passphrase")
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            if status != 200 or not data.get("csrf") or "ms_session" not in cookie:
                raise MeshCoreError("MeshCore login failed")
            self._cookie = cookie["ms_session"].value
            self._csrf = data["csrf"]

    async def request(self, method, path, payload=None):
        if not self._cookie:
            await self.login()
        status, data, _ = await self._request(method, path, payload)
        # Auth failures happen before an action executes, so retrying is safe.
        if status == 401:
            await self.login()
            status, data, _ = await self._request(method, path, payload)
        if status in (401, 403, 428):
            raise MeshCoreAuthError("MeshCore authentication failed")
        if status >= 300 or data.get("error"):
            raise MeshCoreError(data.get("error") or "MeshCore request failed")
        return data
