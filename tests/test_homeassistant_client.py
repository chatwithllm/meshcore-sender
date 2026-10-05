"""Exercise authentication and actions without a radio or HA installation."""

import importlib.util
from pathlib import Path
import unittest

import aiohttp
from aiohttp import web

path = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender/api.py"
spec = importlib.util.spec_from_file_location("meshcore_client", path)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.logins = 0
        self.session_id = None
        self.actions = []
        self.error = None
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.http = aiohttp.ClientSession()
        self.client = api.MeshCoreClient(self.http, f"http://127.0.0.1:{port}", "test-passphrase")

    async def asyncTearDown(self):
        await self.http.close()
        await self.runner.cleanup()

    async def handle(self, request):
        if request.path == "/api/login":
            body = await request.json()
            if body.get("passphrase") != "test-passphrase":
                return web.json_response({"error": "wrong passphrase"}, status=401)
            self.logins += 1
            self.session_id = str(self.logins)
            response = web.json_response({"ok": True, "csrf": "csrf-" + self.session_id})
            response.set_cookie("ms_session", self.session_id)
            return response
        if request.cookies.get("ms_session") != self.session_id or self.session_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        if request.method == "POST":
            if request.headers.get("X-CSRF-Token") != "csrf-" + self.session_id:
                return web.json_response({"error": "bad csrf token"}, status=403)
            if self.error:
                return web.json_response({"error": self.error}, status=409)
            self.actions.append(await request.json())
        return web.json_response({"ok": True, "running": True})

    async def test_starts_requested_target_and_interval(self):
        payload = {"targets": ["dm:OptimusPrime"], "interval": 30, "started_by": "Home Assistant"}
        await self.client.request("POST", "/api/range/start", payload)
        self.assertEqual(self.actions, [payload])
        self.assertEqual(self.logins, 1)

    async def test_server_restart_renews_session_without_duplicate_action(self):
        await self.client.request("GET", "/api/range/status")
        self.session_id = None
        await self.client.request("POST", "/api/range/stop", {})
        self.assertEqual(self.logins, 2)
        self.assertEqual(len(self.actions), 1)

    async def test_rejected_command_is_not_retried(self):
        self.error = "range test already running"
        with self.assertRaisesRegex(api.MeshCoreError, self.error):
            await self.client.request("POST", "/api/range/start", {})
        self.assertEqual(self.logins, 1)
        self.assertEqual(self.actions, [])

    async def test_wrong_passphrase_requires_reauth(self):
        self.client.passphrase = "incorrect"
        with self.assertRaises(api.MeshCoreAuthError):
            await self.client.login()

    def test_rejects_embedded_credentials_and_non_http_urls(self):
        for url in ("http://user:password@localhost:8788", "file:///tmp", "http://host/api?key=x"):
            with self.assertRaises(ValueError):
                api.normalize_url(url)


if __name__ == "__main__":
    unittest.main()
