import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from leasedd.conversion import ConversionError, convert_document, route_converter


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("name", ["a.pdf", "scan.PNG", "photo.jpeg"])
def test_pdf_and_images_route_to_mineru(name):
    assert route_converter(name) == "mineru"


@pytest.mark.parametrize("name", ["a.docx", "table.xlsx", "slides.pptx"])
def test_office_routes_to_markitdown(name):
    assert route_converter(name) == "markitdown"


@pytest.mark.parametrize("name", ["a.txt", "a.md", "a.csv"])
def test_text_routes_to_direct(name):
    assert route_converter(name) == "direct"


def test_direct_conversion_records_hashes_version_and_does_not_change_source(tmp_path):
    source = tmp_path / "资料.md"
    original = "# 资产负债表\n货币资金 100\n".encode()
    source.write_bytes(original)
    output = tmp_path / "converted.md"
    result = convert_document(source, sha(original), output)
    assert result.tool == "direct"
    assert result.tool_version == "utf-8"
    assert result.original_sha256 == sha(original)
    assert result.markdown_sha256 == sha(output.read_bytes())
    assert source.read_bytes() == original
    assert result.status == "completed"


def test_markitdown_conversion_uses_output_file_and_records_version(tmp_path):
    source = tmp_path / "table.xlsx"
    original = b"fake-office"
    source.write_bytes(original)
    output = tmp_path / "table.md"
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if "--version" in command:
            return SimpleNamespace(returncode=0, stdout="markitdown 0.1.6\n", stderr="")
        Path(command[command.index("-o") + 1]).write_text("# 资产负债表\n|货币资金|100|", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = convert_document(source, sha(original), output, runner=runner)
    assert result.tool == "markitdown"
    assert result.tool_version == "0.1.6"
    assert "货币资金" in output.read_text()
    assert any(str(source) in call for call in calls)


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
    def json(self):
        return self._payload


class MinerUClient:
    def __init__(self):
        self.polls = 0
    def post(self, url, **kwargs):
        assert url.endswith("/tasks")
        assert kwargs["files"][0][0] == "files"
        return Response(202, {"task_id": "task-1"})
    def get(self, url):
        if url.endswith("/result"):
            return Response(200, {"result": {"markdown": "# 合并利润表\n净利润 88"}})
        self.polls += 1
        return Response(200, {"status": "completed"})


def test_mineru_conversion_polls_and_extracts_markdown(tmp_path):
    source = tmp_path / "report.pdf"
    original = b"%PDF-fake"
    source.write_bytes(original)
    output = tmp_path / "report.md"
    result = convert_document(source, sha(original), output, mineru_url="http://mineru:8000", http_client=MinerUClient(), sleep=lambda _: None)
    assert result.tool == "mineru"
    assert result.tool_version == "unknown"
    assert output.read_text() == "# 合并利润表\n净利润 88"


def test_changed_original_discards_generated_markdown(tmp_path):
    source = tmp_path / "table.docx"
    original = b"original"
    source.write_bytes(original)
    output = tmp_path / "table.md"
    def runner(command, **kwargs):
        if "--version" in command:
            return SimpleNamespace(returncode=0, stdout="markitdown 0.1.6", stderr="")
        Path(command[command.index("-o") + 1]).write_text("converted")
        source.write_bytes(b"tampered")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    with pytest.raises(ConversionError, match="source_hash_changed"):
        convert_document(source, sha(original), output, runner=runner)
    assert not output.exists()


def test_failed_conversion_has_stable_reason_and_no_partial_output(tmp_path):
    source = tmp_path / "table.xlsx"
    source.write_bytes(b"broken")
    output = tmp_path / "table.md"
    def runner(command, **kwargs):
        if "--version" in command:
            return SimpleNamespace(returncode=0, stdout="markitdown 0.1.6", stderr="")
        return SimpleNamespace(returncode=2, stdout="", stderr="sensitive body must not leak")
    with pytest.raises(ConversionError, match="markitdown_failed"):
        convert_document(source, sha(b"broken"), output, runner=runner)
    assert not output.exists()


def test_unsupported_extension_is_explicit():
    with pytest.raises(ConversionError, match="unsupported_format"):
        route_converter("legacy.doc")
