"""Live M2 smoke test. Creates an isolated project on the configured local stack."""
import json
import os
import time
from pathlib import Path

import httpx


base = os.getenv("LEASEDD_BROWSER_URL", "http://127.0.0.1:5173").rstrip("/") + "/api"
admin = os.environ["LEASEDD_BROWSER_ADMIN"]
password = os.environ["LEASEDD_BROWSER_PASSWORD"]
fixture = Path(os.getenv("LEASEDD_M2_FIXTURE", "fixtures/m2/deidentified_balance.docx"))
suffix = str(int(time.time()))
writer, reviewer = "m2-writer-" + suffix, "m2-reviewer-" + suffix


def login(client, username):
    response = client.post(base + "/login", json={"username": username, "password": password})
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]


with httpx.Client(timeout=30) as client:
    login(client, admin)
    ids = []
    for username in (writer, reviewer):
        response = client.post(base + "/users", json={"username": username, "password": password, "admin": False})
        response.raise_for_status(); ids.append(response.json()["id"])
    response = client.post(base + "/projects", json={"name": "M2 脱敏实测 " + suffix, "writer_id": ids[0], "reviewer_id": ids[1]})
    response.raise_for_status(); project_id = response.json()["id"]
    client.post(base + "/logout").raise_for_status(); login(client, writer)
    with fixture.open("rb") as stream:
        response = client.post(base + f"/projects/{project_id}/documents", files={"file": (fixture.name, stream)}, data={"model_allowed": "true"})
    response.raise_for_status(); document_id = response.json()["id"]
    response = client.post(base + f"/projects/{project_id}/documents/recognize", json={"document_ids": [document_id], "model_allowed": True})
    response.raise_for_status()
    deadline = time.monotonic() + 240
    task = None
    while time.monotonic() < deadline:
        tasks = client.get(base + f"/projects/{project_id}/tasks").json()
        task = next(t for t in tasks if t["kind"] == "extract_finance" and t["result"].get("document_id") == document_id)
        if task["state"] in {"completed", "failed", "stale"}: break
        time.sleep(2)
    assert task and task["state"] == "completed", task
    markdown = client.get(base + f"/projects/{project_id}/documents/{document_id}/markdown")
    markdown.raise_for_status()
    statements = client.get(base + f"/projects/{project_id}/financial-statements").json()
    assert statements and sum(len(s["items"]) for s in statements) > 0, statements
    result = {
        "status": "passed", "project_id": project_id, "document_id": document_id,
        "fixture": fixture.name, "task": task["state"], "statements": len(statements),
        "items": sum(len(s["items"]) for s in statements),
        "verified_items": sum(i["status"] == "source_verified" for s in statements for i in s["items"]),
        "markdown_sha256": markdown.json()["markdown_sha256"],
    }
    Path("runtime/m2/live-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
