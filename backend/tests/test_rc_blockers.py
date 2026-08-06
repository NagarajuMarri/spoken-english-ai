from fastapi.testclient import TestClient
from sqlalchemy import func, select
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.models import BetaFeedback, BetaWaitlistEntry

def registration(email="learner@example.com", invitation_code=None):
    return {"email":email,"password":"StrongPassword123!","display_name":"Anusha","invitation_code":invitation_code}

def test_closed_beta_access_paths_and_waitlist(tmp_path):
    settings=Settings(database_url=f"sqlite:///{(tmp_path/'beta.db').as_posix()}",environment="test",jwt_secret="test-signing-secret-at-least-32-bytes-long",auto_create_tables=True,closed_beta_enabled=True,beta_invite_codes="ALPHA,BETA",beta_allowlist="allowed@example.com",founder_emails="founder@example.com",_env_file=None)
    app=create_app(settings)
    with TestClient(app) as client:
        denied=client.post("/api/v1/auth/register",json=registration("waiting@example.com"))
        assert denied.status_code==403 and "waiting list" in denied.json()["error"]["message"].lower()
        with app.state.session_factory() as session: assert session.scalar(select(func.count()).select_from(BetaWaitlistEntry))==1
        assert client.post("/api/v1/auth/register",json=registration("code@example.com","BETA")).status_code==201
        assert client.post("/api/v1/auth/register",json=registration("allowed@example.com")).status_code==201
        assert client.post("/api/v1/auth/register",json=registration("founder@example.com")).status_code==201
    app.state.engine.dispose()

def test_feedback_subscription_progress_and_founder_authorization(client, learner):
    response=client.post("/api/v1/launch/feedback",json={"rating":5,"category":"voice","severity":"HIGH","message":"Microphone stopped unexpectedly","contact_allowed":True,"screenshot_name":"../private.png"})
    assert response.status_code==202
    with client.app.state.session_factory() as session:
        item=session.scalar(select(BetaFeedback)); assert item.screenshot_name=="private.png" and item.contact_allowed is True
    free=client.get("/api/v1/launch/subscription").json(); assert free["status"]=="FREE" and free["payment_mode"]=="test"
    assert client.post("/api/v1/launch/subscription/trial").status_code==201
    assert client.get("/api/v1/launch/subscription").json()["status"]=="TRIAL"
    assert client.post("/api/v1/launch/subscription/upgrade").json()["real_charge"] is False
    progress=client.get("/api/v1/launch/progress").json(); assert all(value is None for value in progress["scores"].values())
    assert client.get("/api/v1/launch/founder-dashboard").status_code==403

def test_founder_dashboard_read_only(tmp_path):
    settings=Settings(database_url=f"sqlite:///{(tmp_path/'founder.db').as_posix()}",environment="test",jwt_secret="test-signing-secret-at-least-32-bytes-long",auto_create_tables=True,founder_emails="founder@example.com",_env_file=None)
    app=create_app(settings)
    with TestClient(app) as client:
        founder=client.post("/api/v1/auth/register",json=registration("founder@example.com")).json(); client.headers["Authorization"]=f"Bearer {founder['tokens']['access_token']}"
        result=client.get("/api/v1/launch/founder-dashboard"); assert result.status_code==200 and result.json()["read_only"] is True
    app.state.engine.dispose()
