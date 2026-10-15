from pathlib import Path

from isso_facilita.desktop_control import read_ai_enabled, write_ai_enabled


def test_write_ai_enabled_changes_only_requested_value(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    original = (
        "TELEGRAM_BOT_TOKEN=segredo-que-deve-ser-preservado\n"
        "AI_CURATION_ENABLED=false # controle local\n"
        "OLLAMA_MODEL=qwen3-vl:2b-instruct\n"
    )
    env_path.write_text(original, encoding="utf-8")

    write_ai_enabled(True, env_path)

    assert env_path.read_text(encoding="utf-8") == original.replace(
        "AI_CURATION_ENABLED=false", "AI_CURATION_ENABLED=true"
    )
    assert read_ai_enabled(env_path) is True


def test_write_ai_enabled_preserves_bom_and_crlf(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    original = (
        b"\xef\xbb\xbfDRY_RUN=false\r\n"
        b"AI_CURATION_ENABLED=true\r\n"
        b"WHATSAPP_WEB_BRIDGE_TOKEN=preservar\r\n"
    )
    env_path.write_bytes(original)

    write_ai_enabled(False, env_path)

    assert env_path.read_bytes() == original.replace(
        b"AI_CURATION_ENABLED=true", b"AI_CURATION_ENABLED=false"
    )


def test_write_ai_enabled_appends_missing_setting(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("DRY_RUN=true", encoding="utf-8")

    write_ai_enabled(False, env_path)

    assert env_path.read_text(encoding="utf-8") == (
        "DRY_RUN=true\nAI_CURATION_ENABLED=false\n"
    )
    assert read_ai_enabled(env_path) is False


def test_write_ai_enabled_normalizes_duplicate_setting(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "AI_CURATION_ENABLED=false\nAI_CURATION_ENABLED=true\n", encoding="utf-8"
    )

    write_ai_enabled(False, env_path)

    assert env_path.read_text(encoding="utf-8") == (
        "AI_CURATION_ENABLED=false\nAI_CURATION_ENABLED=false\n"
    )


def test_read_ai_enabled_accepts_quoted_boolean(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text('AI_CURATION_ENABLED="yes"\n', encoding="utf-8")

    assert read_ai_enabled(env_path) is True


def test_read_ai_enabled_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert read_ai_enabled(tmp_path / ".env") is None
