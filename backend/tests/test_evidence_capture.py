"""Phase 4.2: console/network evidence capture, verified against the real
shape @playwright/test's JSON reporter produces (confirmed by actually
compiling and running a spec — see script_compiler tests for the render
side). Small attachments arrive as base64 `body`, not a file `path`."""
import base64
import json
from pathlib import Path

from app.services.automation_runner.local_playwright import LocalPlaywrightRunner


def _b64(obj) -> str:
    return base64.b64encode(json.dumps(obj).encode("utf-8")).decode("ascii")


def test_lifts_console_and_network_logs_from_inline_body(tmp_path):
    runner = LocalPlaywrightRunner()
    attachments = [
        {"name": "console-logs.json", "contentType": "application/json", "body": _b64([{"type": "log", "text": "hi"}])},
        {"name": "network-logs.json", "contentType": "application/json", "body": _b64([{"url": "https://x/", "status": 200, "method": "GET"}])},
    ]
    console_logs, network_logs = runner._lift_json_evidence(attachments, tmp_path)
    assert console_logs == [{"type": "log", "text": "hi"}]
    assert network_logs == [{"url": "https://x/", "status": 200, "method": "GET"}]


def test_falls_back_to_path_when_no_inline_body(tmp_path):
    runner = LocalPlaywrightRunner()
    log_file = tmp_path / "console-logs.json"
    log_file.write_text(json.dumps([{"type": "error", "text": "boom"}]), encoding="utf-8")
    attachments = [
        {"name": "console-logs.json", "contentType": "application/json", "path": "console-logs.json"},
    ]
    console_logs, network_logs = runner._lift_json_evidence(attachments, tmp_path)
    assert console_logs == [{"type": "error", "text": "boom"}]
    assert network_logs is None


def test_ignores_non_json_and_unrelated_attachments(tmp_path):
    runner = LocalPlaywrightRunner()
    attachments = [
        {"name": "screenshot.png", "contentType": "image/png", "path": "screenshot.png"},
        {"name": "trace.zip", "contentType": "application/zip", "path": "trace.zip"},
    ]
    console_logs, network_logs = runner._lift_json_evidence(attachments, tmp_path)
    assert console_logs is None
    assert network_logs is None


def test_path_traversal_outside_workspace_is_rejected(tmp_path):
    runner = LocalPlaywrightRunner()
    outside = tmp_path.parent / "escaped-console-logs.json"
    outside.write_text(json.dumps([{"type": "log", "text": "leaked"}]), encoding="utf-8")
    attachments = [
        {"name": "console-logs.json", "contentType": "application/json", "path": "../escaped-console-logs.json"},
    ]
    console_logs, _ = runner._lift_json_evidence(attachments, tmp_path)
    assert console_logs is None
    outside.unlink()


def test_malformed_base64_body_does_not_crash(tmp_path):
    runner = LocalPlaywrightRunner()
    attachments = [
        {"name": "console-logs.json", "contentType": "application/json", "body": "not-valid-base64!!!"},
    ]
    console_logs, network_logs = runner._lift_json_evidence(attachments, tmp_path)
    assert console_logs is None
    assert network_logs is None
