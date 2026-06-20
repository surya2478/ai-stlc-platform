"""GAP-1 tests: image uploads, vision provider plumbing, UI analysis agent wiring."""
import anyio
import pytest
from fastapi import HTTPException

from app.llm import provider as llm_provider
from app.services.document_service import ALLOWED_TYPES, EXT_MAP, IMAGE_TYPES, validate_file_signature
from app.worker.tasks import agent_tasks


# ── GAP-1b: image upload validation ───────────────────────────────────────────

def test_image_types_whitelisted():
    assert ALLOWED_TYPES["image/png"] == "png"
    assert ALLOWED_TYPES["image/jpeg"] == "jpg"
    assert ALLOWED_TYPES["image/webp"] == "webp"
    assert EXT_MAP[".png"] == "png"
    assert EXT_MAP[".jpeg"] == "jpg"
    assert IMAGE_TYPES == {"png", "jpg", "webp"}


def test_png_signature_accepted():
    validate_file_signature("png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)  # no raise


def test_png_signature_rejects_fake():
    with pytest.raises(HTTPException) as exc_info:
        validate_file_signature("png", b"GIF89a not a png")
    assert exc_info.value.status_code == 415


def test_jpg_and_webp_signatures():
    validate_file_signature("jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 16)
    validate_file_signature("webp", b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8)
    with pytest.raises(HTTPException):
        validate_file_signature("webp", b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 8)


def test_existing_document_signatures_unchanged():
    validate_file_signature("pdf", b"%PDF-1.7 rest")
    validate_file_signature("docx", b"PK\x03\x04" + b"\x00" * 16)
    validate_file_signature("txt", b"plain text content")


# ── GAP-1a: vision provider plumbing ──────────────────────────────────────────

def test_ollama_vision_message_shape(monkeypatch):
    captured = {}

    p = llm_provider.OllamaProvider(base_url="http://x", model="llava")

    async def fake_achat(messages, **kwargs):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(p, "achat", fake_achat)
    result = anyio.run(p.generate_vision, "sys", "user prompt", ["B64DATA"])
    assert result == "ok"
    user_msg = captured["messages"][1]
    assert user_msg["role"] == "user"
    assert user_msg["images"] == ["B64DATA"]


def test_openai_vision_message_shape(monkeypatch):
    captured = {}

    p = llm_provider.OpenAICompatibleProvider(api_key="k", base_url="http://x/v1", model="gpt-4o-mini")

    async def fake_achat(messages, **kwargs):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(p, "achat", fake_achat)
    result = anyio.run(p.generate_vision, "sys", "user prompt", ["B64DATA"])
    assert result == "ok"
    content = captured["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "user prompt"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,B64DATA")


def test_get_vision_llm_uses_vision_model():
    llm_provider.get_vision_llm.cache_clear()
    llm = llm_provider.get_vision_llm(provider="ollama", model="qwen2.5vl")
    assert llm.model == "qwen2.5vl"


def test_validate_vision_configuration_accepts_ollama():
    assert llm_provider.validate_vision_configuration(provider="ollama", model="llava") is None


def test_validate_vision_configuration_rejects_huggingface():
    message = llm_provider.validate_vision_configuration(provider="huggingface", model="meta-llama/Llama-3.1-8B-Instruct")
    assert message is not None
    assert "not supported" in message


def test_validate_vision_configuration_rejects_unvalidated_provider():
    message = llm_provider.validate_vision_configuration(provider="cerebras", model="llava")
    assert message is not None
    assert "current provider 'cerebras'" in message


# ── GAP-1c: worker wiring ─────────────────────────────────────────────────────

def test_ui_image_analysis_in_agent_registry():
    assert "ui_image_analysis" in agent_tasks.AGENT_REGISTRY


def test_ui_image_analysis_task_uses_agent_signature(monkeypatch):
    calls = {}

    class FakeUIAgent:
        async def run(self, image_path, image_name="screenshot", context_note="", project_id=0):
            calls.update(
                image_path=image_path,
                image_name=image_name,
                context_note=context_note,
                project_id=project_id,
            )
            return {"ok": True}

    monkeypatch.setattr(agent_tasks, "UIAnalysisAgent", lambda: FakeUIAgent())

    result = anyio.run(
        agent_tasks._ui_image_analysis,
        {
            "image_path": "/storage/uploads/1/x.png",
            "image_name": "login.png",
            "context_note": "Login screen",
            "project_id": 9,
        },
    )
    assert result == {"ok": True}
    assert calls["image_path"] == "/storage/uploads/1/x.png"
    assert calls["project_id"] == 9


# ── GAP-1: JSON block parsing in the UI agent ─────────────────────────────────

def test_ui_agent_json_parsing():
    from app.agents.requirement.ui_analysis_agent import _parse_json_block

    assert _parse_json_block('{"a": 1}') == {"a": 1}
    assert _parse_json_block('Here you go:\n[{"a": 1}]\nthanks') == [{"a": 1}]
    assert _parse_json_block("no json here") is None
