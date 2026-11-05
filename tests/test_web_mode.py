"""Browser-first capabilities keep reading available while omitting desktop management.

These requests use an in-process server with mock jobs: no user's documents, settings,
model services, applications, or installation directories are changed.
"""
import copy
import http.client
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from textfold import server


class WebMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(mock.Mock()))
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def request(self, path, method="GET", host=None, origin=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if origin:
            headers["Origin"] = origin
        connection.request(method, path, body=b"{}" if method == "POST" else None, headers=headers)
        response = connection.getresponse()
        status, payload = response.status, json.loads(response.read())
        connection.close()
        return status, payload

    def test_default_installation_keeps_desktop_capabilities(self):
        with mock.patch.dict(os.environ, {"TEXTFOLD_WEB": ""}):
            status, payload = self.request("/api/capabilities")
        self.assertEqual(status, 200)
        self.assertFalse(payload["web"])
        self.assertTrue(all(value for name, value in payload.items() if name != "web"))

    def test_web_capabilities_are_explicit(self):
        with mock.patch.dict(os.environ, {"TEXTFOLD_WEB": "1"}):
            status, payload = self.request("/api/capabilities")
        self.assertEqual(status, 200)
        self.assertTrue(payload["web"])
        self.assertFalse(any(value for name, value in payload.items() if name != "web"))

    def test_desktop_management_does_not_run_in_web_mode(self):
        paths = ["/api/storage", "/api/engine/install", "/api/engine/remove", "/api/bridge/start",
                 "/api/agents/probe", "/api/agents/save", "/api/agents/remove",
                 "/api/zotero/library", "/api/zotero/read"]
        with mock.patch.dict(os.environ, {"TEXTFOLD_WEB": "1"}):
            for path in paths:
                with self.subTest(path=path):
                    status, payload = self.request(path, "POST")
                    self.assertEqual(status, 403)
                    self.assertEqual(payload["error"], "web-mode")
            for path in ("/api/zotero", "/api/zotero/collections", "/api/zotero/items"):
                self.assertEqual(self.request(path)[0], 403)

    def test_web_bridge_does_not_probe_local_service(self):
        with mock.patch.dict(os.environ, {"TEXTFOLD_WEB": "1"}), mock.patch.object(server.bridges, "bridge_status") as probe:
            self.assertEqual(self.request("/api/bridge"), (200, {"running": False, "node": False}))
            probe.assert_not_called()

    def test_reading_and_existing_agent_discovery_are_not_desktop_management(self):
        for path in ("/api/import", "/api/generate", "/api/notes/a", "/api/export", "/api/providers/save",
                     "/api/models/refresh", "/api/agents/scan", "/api/convert"):
            self.assertFalse(server.desktop_route(path, "POST"), path)

    def test_host_and_origin_guards_apply_to_web_mode(self):
        with mock.patch.dict(os.environ, {"TEXTFOLD_WEB": "1"}):
            self.assertEqual(self.request("/api/capabilities", host="untrusted.example")[0], 421)
            status, payload = self.request("/api/storage", "POST", origin="https://untrusted.example")
            self.assertEqual((status, payload["error"]), (403, "forbidden"))

    def test_web_refresh_keeps_ollama_without_chatgpt_bridge_probe(self):
        class InlineThread:
            def __init__(self, target, **kwargs):
                self.target = target

            def start(self):
                self.target()

        discovery = copy.deepcopy(server.DISCOVERY)
        discovery["refreshing"] = False
        with mock.patch.dict(os.environ, {"TEXTFOLD_WEB": "1", "TEXTFOLD_NO_MODELS": ""}), \
             mock.patch.object(server, "DISCOVERY", discovery), \
             mock.patch.object(server.threading, "Thread", InlineThread), \
             mock.patch.object(server.providers, "ollama_models", return_value=[]) as ollama, \
             mock.patch.object(server.bridges, "bridge_status") as bridge:
            server.refresh_models()
            ollama.assert_called_once_with(strict=True)
            bridge.assert_not_called()
            self.assertIsNone(discovery["live"]["bridge"])
            self.assertFalse(discovery["refreshing"])


if __name__ == "__main__":
    unittest.main()
