"""
Cloud-Based Student Task Manager
Cloud Computing Laboratory Assignment 8 Mini Project

Backend: Python Flask with in-memory task storage.
WSGI Production: Gunicorn (single worker configuration).
"""

import os
import sys
import logging
from datetime import datetime, timezone
from threading import Lock
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash

# -----------------------------------------------------------------------------
# Configuration and Logging Setup
# -----------------------------------------------------------------------------
# Safe structured logging to stdout. Secrets or sensitive credentials are never logged.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [StudentTaskManager] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("student_task_manager")

app = Flask(__name__)
# Secret key for session/flash messages - defaults to a secure fallback for demo
app.secret_key = os.environ.get("SECRET_KEY", "student-task-manager-dev-key-change-in-prod")

# -----------------------------------------------------------------------------
# In-Memory Storage Engine
# -----------------------------------------------------------------------------
# NOTE FOR CLOUD DEPLOYMENT & EVALUATION:
# In-memory storage is ephemeral. Because memory address spaces are not shared
# across processes, Gunicorn MUST run with exactly 1 worker (-w 1).
# Multi-worker configurations or multi-instance autoscaling would cause state
# desynchronization because requests would land on isolated process memories.
task_lock = Lock()
tasks = []
task_id_counter = 1


def get_all_tasks():
    """Retrieve all tasks in reverse chronological order."""
    with task_lock:
        return list(reversed(tasks))


def get_task_stats():
    """Calculate summary statistics for dashboard badges."""
    with task_lock:
        total = len(tasks)
        completed = sum(1 for t in tasks if t["completed"])
        pending = total - completed
        percent = int((completed / total) * 100) if total > 0 else 0
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "percent": percent
        }


def find_task_by_id(task_id):
    """Find a single task by ID."""
    with task_lock:
        for t in tasks:
            if t["id"] == task_id:
                return t
    return None


def reset_tasks():
    """Helper method primarily used by the test suite to ensure test isolation."""
    global tasks, task_id_counter
    with task_lock:
        tasks = []
        task_id_counter = 1


# -----------------------------------------------------------------------------
# Routes & Controllers
# -----------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    """Render modern student task management dashboard."""
    return render_template(
        "index.html",
        tasks=get_all_tasks(),
        stats=get_task_stats()
    ), 200


@app.route("/health", methods=["GET"])
def health():
    """
    Health check endpoint for cloud load balancers and container orchestrators.
    Returns JSON status healthy with HTTP 200.
    """
    with task_lock:
        total_tasks = len(tasks)

    logger.info("Health check ping received. System status: healthy.")
    return jsonify({
        "status": "healthy",
        "service": "student-task-manager",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tasks_count": total_tasks
    }), 200


@app.route("/tasks", methods=["POST"])
def add_task():
    """
    Create a new student task with input validation:
    - Rejects empty or whitespace-only task titles.
    - Rejects task titles exceeding 120 characters.
    """
    global task_id_counter

    # Support both standard form submission and JSON requests
    if request.is_json:
        data = request.get_json(silent=True) or {}
        title = data.get("title", "")
    else:
        title = request.form.get("title", "")

    title_clean = title.strip()

    # Rule 1: Validate empty title
    if not title_clean:
        logger.warning("Task validation failed: Title is empty or whitespace.")
        if request.is_json:
            return jsonify({
                "status": "error",
                "message": "Task title cannot be empty."
            }), 400
        flash("Task title cannot be empty.", "error")
        return render_template(
            "index.html",
            tasks=get_all_tasks(),
            stats=get_task_stats(),
            form_error="Task title cannot be empty."
        ), 400

    # Rule 2: Validate max length (120 characters)
    if len(title_clean) > 120:
        logger.warning(
            "Task validation failed: Title length (%d) exceeds 120 characters.",
            len(title_clean)
        )
        if request.is_json:
            return jsonify({
                "status": "error",
                "message": "Task title cannot exceed 120 characters."
            }), 400
        flash("Task title cannot exceed 120 characters.", "error")
        return render_template(
            "index.html",
            tasks=get_all_tasks(),
            stats=get_task_stats(),
            form_error="Task title cannot exceed 120 characters."
        ), 400

    # Valid task creation
    with task_lock:
        new_task = {
            "id": task_id_counter,
            "title": title_clean,
            "completed": False,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        tasks.append(new_task)
        assigned_id = task_id_counter
        task_id_counter += 1

    logger.info("Task created successfully: ID=%d, TitleLength=%d", assigned_id, len(title_clean))

    if request.is_json:
        return jsonify({
            "status": "success",
            "message": "Task created successfully.",
            "task": new_task
        }), 201

    flash("Task created successfully!", "success")
    return redirect(url_for("index"))


@app.route("/tasks/<int:task_id>/toggle", methods=["POST"])
def toggle_task(task_id):
    """Toggle a task's completion status (complete/undo)."""
    with task_lock:
        target = None
        for t in tasks:
            if t["id"] == task_id:
                target = t
                break

        if target is None:
            logger.warning("Attempted to toggle non-existent task ID=%d", task_id)
            if request.is_json:
                return jsonify({"status": "error", "message": "Task not found."}), 404
            flash(f"Task #{task_id} not found.", "error")
            return redirect(url_for("index")), 404

        target["completed"] = not target["completed"]
        new_state = "completed" if target["completed"] else "pending"

    logger.info("Task ID=%d status toggled to %s.", task_id, new_state)

    if request.is_json:
        return jsonify({
            "status": "success",
            "message": f"Task toggled to {new_state}.",
            "task": target
        }), 200

    return redirect(url_for("index"))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):
    """Delete a task from the in-memory store."""
    global tasks
    deleted = False

    with task_lock:
        original_count = len(tasks)
        tasks = [t for t in tasks if t["id"] != task_id]
        if len(tasks) < original_count:
            deleted = True

    if not deleted:
        logger.warning("Attempted to delete non-existent task ID=%d", task_id)
        if request.is_json:
            return jsonify({"status": "error", "message": "Task not found."}), 404
        flash(f"Task #{task_id} not found.", "error")
        return redirect(url_for("index")), 404

    logger.info("Task ID=%d permanently deleted.", task_id)

    if request.is_json:
        return jsonify({
            "status": "success",
            "message": "Task deleted successfully."
        }), 200

    flash("Task deleted successfully.", "info")
    return redirect(url_for("index"))


# -----------------------------------------------------------------------------
# Error Handlers
# -----------------------------------------------------------------------------
@app.errorhandler(404)
def handle_404_error(e):
    """
    Handle HTTP 404 Not Found for both HTML and JSON consumers.
    """
    logger.info("404 Not Found triggered for path: %s", request.path)
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({
            "status": "error",
            "error": "Not Found",
            "message": f"The requested URL '{request.path}' was not found on this server."
        }), 404

    return render_template(
        "index.html",
        tasks=get_all_tasks(),
        stats=get_task_stats(),
        not_found_path=request.path
    ), 404


@app.errorhandler(500)
def handle_500_error(e):
    """Handle internal server errors safely without exposing tracebacks to end users."""
    logger.error("Internal Server Error occurred: %s", str(e), exc_info=True)
    if request.is_json:
        return jsonify({
            "status": "error",
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later."
        }), 500
    return "<h1>500 - Internal Server Error</h1><p>An unexpected error occurred.</p>", 500


# -----------------------------------------------------------------------------
# Local Development Entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Disable debug mode outside local development explicitly
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
    
    logger.info("Starting Student Task Manager locally on port %d (debug=%s)", port, debug_mode)
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
