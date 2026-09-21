"""Exercise authenticated project creation, validation, persistence, and scoping."""

import unittest
from urllib.parse import quote

from tests.support import MATRIX_NAME, running_server


def project_payload(client, name="First project", plan=None):
    """Build a complete upload from disposable collection-plan fixtures."""
    matrix = (client.root / f"{MATRIX_NAME}.csv").read_text()
    batches = (client.root / f"{MATRIX_NAME}_batches.csv").read_text()
    if plan:
        batches = batches.replace("colour_print_enhancement_2", plan)
        matrix = matrix.replace(MATRIX_NAME, plan)
    return dict(name=name, matrix_csv=matrix, batches_csv=batches)


class ProjectTests(unittest.TestCase):
    """Run against real HTTP handlers and isolated state directories."""

    def test_creation_selection_and_restart(self):
        """Two projects retain different plans and captures across a server restart."""
        with running_server() as client:
            status, first, _ = client.request("/api/projects", project_payload(client))
            self.assertEqual(status, 200)
            status, second, _ = client.request(
                "/api/projects", project_payload(client, "Second", "other")
            )
            self.assertEqual(status, 200)
            for project, count in ((first, 5), (second, 0)):
                query = "?project=" + project["id"]
                self.assertEqual(len(client.request("/api/captures" + query)[1]), count)
                self.assertEqual(
                    client.request("/api/search" + query + "&q=capture")[1]["total"],
                    count,
                )
                self.assertEqual(
                    client.request("/api/matrix" + query)[1][0]["matrix_name"],
                    project["matrix_name"],
                )
            self.assertEqual(len(client.request("/api/captures")[1]), 5)
            self.assertEqual(len(client.request("/api/projects")[1]), 3)
            client.restart()
            self.assertEqual(
                client.request("/api/project?project=" + second["id"])[1]["name"],
                "Second",
            )
            self.assertEqual(client.request("/projects.html")[0], 200)
            self.assertEqual(
                client.request("/api/projects", project_payload(client))[0], 400
            )

    def test_invalid_upload_is_atomic(self):
        """Bad PINs, malformed CSVs, and inconsistent pairs never create a project."""
        with running_server() as client:
            payload = project_payload(client)
            self.assertEqual(
                client.request("/api/projects", payload, token="wrong")[0], 403
            )
            for changes in (
                {"name": " "},
                {"matrix_csv": ""},
                {"batches_csv": "batch_name\ngenuine\n"},
                {"matrix_csv": payload["matrix_csv"].replace("genuine", "missing")},
                {"matrix_csv": payload["matrix_csv"].replace(",5", ",-1")},
                {"matrix_csv": payload["matrix_csv"] + "short,row\n"},
                {
                    "matrix_csv": payload["matrix_csv"]
                    + payload["matrix_csv"].splitlines()[1]
                },
                {"batches_csv": "x" * 400001},
            ):
                with self.subTest(changes=list(changes)):
                    self.assertEqual(
                        client.request("/api/projects", {**payload, **changes})[0], 400
                    )
                    self.assertEqual(len(client.request("/api/projects")[1]), 1)
            self.assertEqual(
                client.request(
                    "/api/projects",
                    {**payload, "matrix_csv": "\ufeff" + payload["matrix_csv"]},
                )[0],
                200,
            )

    def test_unknown_and_cross_project_requests(self):
        """Invalid project IDs cannot escape storage or read and modify other captures."""
        with running_server() as client:
            for identifier in ("unknown", "../secret", "0" * 32):
                for route in ("matrix", "batches", "captures", "quality"):
                    self.assertEqual(
                        client.request(f"/api/{route}?project={quote(identifier)}")[0],
                        400,
                    )
            project = client.request(
                "/api/projects", project_payload(client, plan="other")
            )[1]
            query = "?project=" + project["id"]
            key = "genuine/capture-0/capture-0.jpg"
            self.assertEqual(
                client.request("/api/capture" + query + "&key=" + quote(key))[0], 404
            )
            self.assertEqual(
                client.request(
                    "/api/quality" + query,
                    {"key": key, "status": "pass", "expected": None},
                )[0],
                400,
            )
            self.assertEqual(client.request("/api/quality")[1], {})

    def test_new_install_without_legacy_plans(self):
        """A fresh dataset can create and open its first project without legacy CSVs."""
        with running_server() as client:
            payload = project_payload(client)
            for suffix in ("", "_batches"):
                (client.root / f"{MATRIX_NAME}{suffix}.csv").unlink()
            self.assertEqual(client.request("/api/projects")[1], [])
            project = client.request("/api/projects", payload)[1]
            self.assertEqual(
                client.request("/api/matrix?project=" + project["id"])[0], 200
            )
