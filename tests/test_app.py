"""
Automated Test Suite for Cloud-Based Student Task Manager
Cloud Computing Laboratory Assignment 8

Framework: Python standard library `unittest`
Verifies:
  1. Homepage status and HTML content
  2. Health check endpoint (status code 200, JSON schema)
  3. Task creation with valid inputs
  4. Task creation validation: empty title rejection (HTTP 400)
  5. Task creation validation: excessive length (>120 chars) rejection (HTTP 400)
  6. Task completion toggle and undo functionality
  7. Task deletion
  8. Non-existent task action handling (HTTP 404)
  9. Unknown URL / routing error handling (HTTP 404)
 10. Safe Jinja template rendering (XSS auto-escaping)
"""

import unittest
import json
import os
import sys

# Ensure parent directory is in sys.path so app can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app, reset_tasks, tasks


class StudentTaskManagerTestCase(unittest.TestCase):
    """Test cases for Student Task Manager Flask application."""

    def setUp(self):
        """Configure test client and isolate in-memory state before each test."""
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        reset_tasks()

    def tearDown(self):
        """Clean up state after each test."""
        reset_tasks()

    def test_01_homepage_renders_successfully(self):
        """Test GET / returns HTTP 200 and renders the student dashboard."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        content = response.data.decode("utf-8")
        self.assertIn("Cloud-Based Student Task Manager", content)
        self.assertIn("Add New Student Task", content)
        self.assertIn("Total Tasks", content)

    def test_02_health_endpoint(self):
        """Test GET /health returns HTTP 200 and valid JSON with healthy status."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")

        data = json.loads(response.data)
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("service"), "student-task-manager")
        self.assertIn("timestamp", data)
        self.assertEqual(data.get("tasks_count"), 0)

    def test_03_task_creation_valid(self):
        """Test creating a valid task via form POST and JSON POST."""
        # Test form submission
        form_response = self.client.post(
            "/tasks",
            data={"title": "Submit Assignment 8 Report"},
            follow_redirects=True
        )
        self.assertEqual(form_response.status_code, 200)
        content = form_response.data.decode("utf-8")
        self.assertIn("Submit Assignment 8 Report", content)

        # Test JSON API creation
        json_response = self.client.post(
            "/tasks",
            json={"title": "Prepare Presentation Slides"},
            content_type="application/json"
        )
        self.assertEqual(json_response.status_code, 201)
        json_data = json.loads(json_response.data)
        self.assertEqual(json_data.get("status"), "success")
        self.assertEqual(json_data["task"]["title"], "Prepare Presentation Slides")
        self.assertFalse(json_data["task"]["completed"])

    def test_04_task_creation_empty_rejected(self):
        """Test empty and whitespace-only task titles return HTTP 400."""
        # Form submission with empty string
        res_empty = self.client.post("/tasks", data={"title": ""})
        self.assertEqual(res_empty.status_code, 400)
        self.assertIn("Task title cannot be empty.", res_empty.data.decode("utf-8"))

        # Form submission with whitespace only
        res_spaces = self.client.post("/tasks", data={"title": "     "})
        self.assertEqual(res_spaces.status_code, 400)
        self.assertIn("Task title cannot be empty.", res_spaces.data.decode("utf-8"))

        # JSON submission with empty string
        res_json = self.client.post("/tasks", json={"title": "  "})
        self.assertEqual(res_json.status_code, 400)
        json_data = json.loads(res_json.data)
        self.assertEqual(json_data.get("message"), "Task title cannot be empty.")

    def test_05_task_creation_exceeds_120_chars_rejected(self):
        """Test task title exceeding 120 characters returns HTTP 400."""
        too_long_title = "A" * 121

        # Form submission
        res_form = self.client.post("/tasks", data={"title": too_long_title})
        self.assertEqual(res_form.status_code, 400)
        self.assertIn("Task title cannot exceed 120 characters.", res_form.data.decode("utf-8"))

        # JSON submission
        res_json = self.client.post("/tasks", json={"title": too_long_title})
        self.assertEqual(res_json.status_code, 400)
        json_data = json.loads(res_json.data)
        self.assertEqual(json_data.get("message"), "Task title cannot exceed 120 characters.")

        # Exactly 120 characters should succeed
        exact_120_title = "B" * 120
        res_exact = self.client.post("/tasks", json={"title": exact_120_title})
        self.assertEqual(res_exact.status_code, 201)

    def test_06_toggle_task_completion_and_undo(self):
        """Test toggling task completion between pending and completed."""
        # Create a task
        self.client.post("/tasks", json={"title": "Study Virtualization Architectures"})
        task_id = 1

        # Toggle to completed
        toggle_res_1 = self.client.post(f"/tasks/{task_id}/toggle", json={})
        self.assertEqual(toggle_res_1.status_code, 200)
        data_1 = json.loads(toggle_res_1.data)
        self.assertTrue(data_1["task"]["completed"])

        # Toggle back to pending (undo)
        toggle_res_2 = self.client.post(f"/tasks/{task_id}/toggle", json={})
        self.assertEqual(toggle_res_2.status_code, 200)
        data_2 = json.loads(toggle_res_2.data)
        self.assertFalse(data_2["task"]["completed"])

    def test_07_task_deletion(self):
        """Test deleting a task removes it from memory and dashboard."""
        # Create two tasks
        self.client.post("/tasks", json={"title": "Task One"})
        self.client.post("/tasks", json={"title": "Task Two"})

        # Delete Task 1
        delete_res = self.client.post("/tasks/1/delete", json={})
        self.assertEqual(delete_res.status_code, 200)

        # Health endpoint should reflect 1 task remaining
        health_res = self.client.get("/health")
        health_data = json.loads(health_res.data)
        self.assertEqual(health_data["tasks_count"], 1)

    def test_08_nonexistent_task_operations_return_404(self):
        """Test toggle or delete on invalid ID returns HTTP 404."""
        toggle_res = self.client.post("/tasks/999/toggle", json={})
        self.assertEqual(toggle_res.status_code, 404)

        delete_res = self.client.post("/tasks/999/delete", json={})
        self.assertEqual(delete_res.status_code, 404)

    def test_09_unknown_url_returns_404(self):
        """Test navigating to an unmapped route returns HTTP 404."""
        # Browser request (HTML)
        res_html = self.client.get("/this/route/does/not/exist")
        self.assertEqual(res_html.status_code, 404)
        self.assertIn("HTTP 404", res_html.data.decode("utf-8"))

        # API request (JSON)
        res_json = self.client.get(
            "/api/unknown-endpoint",
            headers={"Accept": "application/json"}
        )
        self.assertEqual(res_json.status_code, 404)
        json_data = json.loads(res_json.data)
        self.assertEqual(json_data.get("status"), "error")
        self.assertEqual(json_data.get("error"), "Not Found")

    def test_10_safe_jinja_rendering_xss_protection(self):
        """Test that user input containing HTML/script tags is safely auto-escaped."""
        xss_payload = "<script>alert('xss')</script>"
        self.client.post("/tasks", data={"title": xss_payload})

        page_res = self.client.get("/")
        content = page_res.data.decode("utf-8")
        # Ensure raw <script> tag is NOT present unescaped
        self.assertNotIn("<script>alert('xss')</script>", content)
        # Ensure Jinja auto-escaped representation is rendered
        self.assertIn("&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;", content)


if __name__ == "__main__":
    unittest.main()
