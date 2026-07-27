from fastapi.testclient import TestClient

from backend.app.core.config import Settings, get_settings
from backend.app.main import create_app


def test_health_returns_200_and_expected_schema() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "spoken-english-ai",
        "version": "0.1.0",
    }
    assert set(response.json()) == {"status", "service", "version"}


def test_configuration_loads_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("SPOKEN_ENGLISH_ENVIRONMENT", "test")
    monkeypatch.setenv("SPOKEN_ENGLISH_DEBUG", "true")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.debug is True


def test_application_starts_with_all_integrations_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SPOKEN_ENGLISH_LLM_PROVIDER", "disabled")
    monkeypatch.setenv("SPOKEN_ENGLISH_SPEECH_TO_TEXT_PROVIDER", "disabled")
    monkeypatch.setenv("SPOKEN_ENGLISH_TEXT_TO_SPEECH_PROVIDER", "disabled")
    get_settings.cache_clear()

    application = create_app()

    assert application.title == "spoken-english-ai"
    assert TestClient(application).get("/health").status_code == 200
    get_settings.cache_clear()

