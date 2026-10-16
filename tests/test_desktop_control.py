from pathlib import Path

import isso_facilita.desktop_control as desktop_control
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


def test_stop_everything_targets_only_project_services(monkeypatch) -> None:
    actions: list[str] = []
    monkeypatch.setattr(desktop_control, "stop_bot", lambda: actions.append("bot"))
    monkeypatch.setattr(
        desktop_control,
        "_stop_listener_service",
        lambda port, _names: actions.append(str(port)),
    )
    monkeypatch.setattr(
        desktop_control,
        "get_service_statuses",
        lambda: {"bot": False, "whatsapp": False, "ollama": False},
    )

    statuses = desktop_control.stop_everything()

    assert actions == ["bot", "3001", "11434"]
    assert not any(statuses.values())


def test_start_everything_uses_safe_service_order(monkeypatch, tmp_path: Path) -> None:
    actions: list[str] = []
    wait_timeouts: list[float] = []
    monkeypatch.setattr(
        desktop_control,
        "start_ollama",
        lambda _root: actions.append("ollama"),
    )
    monkeypatch.setattr(
        desktop_control,
        "start_whatsapp",
        lambda _root: actions.append("whatsapp"),
    )
    monkeypatch.setattr(desktop_control, "get_bot_health", lambda: None)
    monkeypatch.setattr(
        desktop_control,
        "start_bot",
        lambda _root: actions.append("bot"),
    )
    monkeypatch.setattr(
        desktop_control,
        "_wait_for_url",
        lambda url, timeout: (actions.append(url), wait_timeouts.append(timeout)),
    )
    monkeypatch.setattr(
        desktop_control,
        "get_service_statuses",
        lambda: {"bot": True, "whatsapp": True, "ollama": True},
    )

    statuses = desktop_control.start_everything(tmp_path)

    assert actions == ["ollama", "whatsapp", "bot", desktop_control.BOT_URL]
    assert wait_timeouts == [desktop_control.BOT_START_TIMEOUT_SECONDS]
    assert all(statuses.values())
