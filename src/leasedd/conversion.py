import hashlib
import mimetypes
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


class ConversionError(Exception):
    pass


@dataclass(frozen=True)
class ConversionResult:
    status: str
    tool: str
    tool_version: str
    original_sha256: str
    markdown_sha256: str
    markdown_path: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def route_converter(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        return "mineru"
    if suffix in {".docx", ".xlsx", ".pptx"}:
        return "markitdown"
    if suffix in {".txt", ".md", ".markdown", ".csv"}:
        return "direct"
    raise ConversionError("unsupported_format")


def _find_value(payload, names):
    if isinstance(payload, dict):
        for name in names:
            value = payload.get(name)
            if isinstance(value, str) and value:
                return value
        for value in payload.values():
            found = _find_value(value, names)
            if found:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _find_value(value, names)
            if found:
                return found
    return None


def _mineru_markdown(source: Path, original_name: str, base_url: str, client, sleep, timeout: float) -> tuple[str, str]:
    base_url = base_url.rstrip("/")
    content_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    response = client.post(
        base_url + "/tasks",
        files=[("files", (original_name, source.read_bytes(), content_type))],
        data={"return_md": "true", "table_enable": "true", "parse_method": "auto", "lang_list": "ch"},
    )
    if response.status_code not in (200, 202):
        raise ConversionError("mineru_submit_failed")
    payload = response.json()
    task_id = _find_value(payload, {"task_id", "id"})
    if not task_id:
        raise ConversionError("mineru_invalid_response")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status_response = client.get(f"{base_url}/tasks/{task_id}")
        if status_response.status_code >= 400:
            raise ConversionError("mineru_status_failed")
        status_payload = status_response.json()
        status = (_find_value(status_payload, {"status", "state"}) or "").lower()
        if status in {"failed", "error", "cancelled"}:
            raise ConversionError("mineru_parse_failed")
        if status in {"completed", "success", "succeeded", "done"}:
            result = client.get(f"{base_url}/tasks/{task_id}/result")
            if result.status_code >= 400:
                raise ConversionError("mineru_result_failed")
            markdown = _find_value(result.json(), {"markdown", "md_content", "full_md", "md"})
            if markdown is None:
                raise ConversionError("mineru_markdown_missing")
            version = _find_value(status_payload, {"version", "tool_version"}) or "unknown"
            return markdown, version
        sleep(1)
    raise ConversionError("mineru_timeout")


def convert_document(
    source: Path,
    expected_sha256: str,
    output: Path,
    *,
    runner=subprocess.run,
    mineru_url: str | None = None,
    http_client=None,
    sleep=time.sleep,
    timeout: float = 900,
    original_name: str | None = None,
) -> ConversionResult:
    source = Path(source)
    output = Path(output)
    if not source.is_file() or file_sha256(source) != expected_sha256:
        raise ConversionError("source_hash_mismatch")
    original_name = original_name or source.name
    tool = route_converter(original_name)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        if tool == "direct":
            markdown = source.read_text(encoding="utf-8-sig")
            tool_version = "utf-8"
            temporary.write_text(markdown, encoding="utf-8")
        elif tool == "markitdown":
            command = os.getenv("MARKITDOWN_COMMAND", "markitdown")
            version_result = runner([command, "--version"], capture_output=True, text=True, timeout=30)
            version_text = version_result.stdout.strip() if version_result.returncode == 0 else "unknown"
            tool_version = version_text.rsplit(" ", 1)[-1] if version_text else "unknown"
            extension = Path(original_name).suffix.lstrip('.')
            result = runner([command, str(source), "-x", extension, "-o", str(temporary)], capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0 or not temporary.is_file():
                raise ConversionError("markitdown_failed")
        else:
            if not mineru_url:
                mineru_url = os.getenv("MINERU_URL", "http://host.docker.internal:58000")
            if http_client is None:
                import httpx
                with httpx.Client(timeout=60, trust_env=False) as client:
                    markdown, tool_version = _mineru_markdown(source, original_name, mineru_url, client, sleep, timeout)
            else:
                markdown, tool_version = _mineru_markdown(source, original_name, mineru_url, http_client, sleep, timeout)
            temporary.write_text(markdown, encoding="utf-8")
        if file_sha256(source) != expected_sha256:
            raise ConversionError("source_hash_changed")
        if not temporary.is_file():
            raise ConversionError("markdown_missing")
        markdown_sha = file_sha256(temporary)
        temporary.replace(output)
        return ConversionResult("completed", tool, tool_version, expected_sha256, markdown_sha, str(output))
    except ConversionError:
        temporary.unlink(missing_ok=True)
        raise
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        temporary.unlink(missing_ok=True)
        raise ConversionError(f"{tool}_failed") from exc
