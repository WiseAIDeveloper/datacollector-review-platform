"""Runtime configuration and lifecycle checks introduced by the refactor."""

import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import PROJECT, dataset
from ingestion import IngestionLog
from server import create_server
from settings import Settings


class RuntimeTests(unittest.TestCase):
    """Verify explicit configuration, secret redaction, and isolated application state."""

    def test_settings_require_runtime_credential(self):
        """Reject absent or blank credentials before opening any server sockets."""
        for value in (None, "", " "):
            environment = {} if value is None else {"DELETE_TOKEN": value}
            with self.assertRaisesRegex(ValueError, "runtime environment"):
                Settings.from_environment(environment)

    def test_settings_hide_credential_and_validate_port(self):
        """Keep secrets out of settings representations and validate the listening port."""
        token = secrets.token_hex(24)
        settings = Settings.from_environment({"DELETE_TOKEN": token, "PORT": "0"})
        self.assertNotIn(token, repr(settings))
        self.assertEqual(settings.port, 0)
        for port in ("-1", "65536", "invalid"):
            with self.assertRaises(ValueError):
                Settings.from_environment({"DELETE_TOKEN": token, "PORT": port})

    def test_server_import_has_no_runtime_side_effects(self):
        """Importing the server must not read secrets, open databases, or start threads."""
        script = """
from unittest.mock import patch
with patch('sqlite3.connect', side_effect=AssertionError('database opened')):
    with patch('threading.Thread.start', side_effect=AssertionError('thread started')):
        with patch('socket.socket', side_effect=AssertionError('socket opened')):
            import server
"""
        environment = {key: value for key, value in os.environ.items() if key != "DELETE_TOKEN"}
        result = subprocess.run([sys.executable, "-c", script], cwd=PROJECT, env=environment,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_application_instances_do_not_share_dataset_or_secret(self):
        """Construct two applications with separate roots, databases, locks, and credentials."""
        with tempfile.TemporaryDirectory() as temporary:
            servers = []
            try:
                for index in range(2):
                    root = Path(temporary) / str(index)
                    dataset(root, count=index + 1)
                    settings = Settings(root, root / "history.sqlite", root / "history.jsonl",
                                        secrets.token_hex(24), "127.0.0.1", 0)
                    servers.append(create_server(settings))
                self.assertEqual([len(s.application.records()) for s in servers], [1, 2])
                self.assertIsNot(servers[0].application.lock, servers[1].application.lock)
                self.assertNotEqual(servers[0].application.settings.delete_token,
                                    servers[1].application.settings.delete_token)
                self.assertTrue(all(s.application.ingestion.thread is None for s in servers))
            finally:
                for server in servers:
                    server.server_close()
                    server.application.ingestion.close()

    def test_scanner_starts_once_and_stops_before_database_close(self):
        """Repeated starts share one worker, which is joined during shutdown."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset(root, count=1)
            log = IngestionLog(root, root / "history.sqlite")
            try:
                log.start()
                first = log.thread
                log.start()
                self.assertIs(log.thread, first)
            finally:
                log.close()
            self.assertFalse(first.is_alive())


if __name__ == "__main__":
    unittest.main()
