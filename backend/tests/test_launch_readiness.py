from backend.app.core.config import Settings


def test_launch_config_can_be_disabled_and_remains_test_mode(client):
    response = client.get("/api/v1/launch/config")
    assert response.status_code == 200
    assert response.json()["closed_beta"] is False
    assert response.json()["razorpay_mode"] == "test"
    assert response.json()["provider_policy"] == "OPENAI_FIRST"


def test_feedback_requires_authentication(client):
    response = client.post("/api/v1/launch/feedback", json={"rating": 5, "category": "lesson", "severity": "LOW", "message": "Helpful lesson"})
    assert response.status_code == 401


def test_production_rejects_live_razorpay_mode():
    try:
        Settings(environment="production", database_url="postgresql://db/app", auto_create_tables=False,
                 jwt_secret="x" * 48, force_https=True, secure_cookies=True, cors_origins="https://app.example.com",
                 trusted_hosts="app.example.com", object_storage_backend="s3", object_storage_bucket="private",
                 razorpay_enabled=True, razorpay_webhook_secret="test-secret", razorpay_mode="live", _env_file=None)
    except ValueError as exc:
        assert "razorpay_test_mode" in str(exc)
    else:
        raise AssertionError("live Razorpay mode must fail closed")
