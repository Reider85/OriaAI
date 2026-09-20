from fastapi.testclient import TestClient

from llm_client.transport.endpoint import SessionState, build_cancel_router


class FakePublisher:
    def __init__(self):
        self.published = []

    async def publish(self, session_id, reason, user_id=None):
        self.published.append((session_id, reason, user_id))


def _app():
    from fastapi import FastAPI

    app = FastAPI()
    state = SessionState()
    state.activate("active-1")
    state.activate("active-2")
    state.activate("cancelled-1")
    state.mark_cancelled("cancelled-1")
    app.include_router(build_cancel_router(FakePublisher(), state))
    return app, state


def test_cancel_returns_202():
    app, _state = _app()
    client = TestClient(app)
    resp = client.post("/sessions/active-1/cancel", json={"reason": "user_cancelled"})
    assert resp.status_code == 202
    assert resp.json() == {"status": "cancel_queued", "session_id": "active-1"}


def test_cancel_404_unknown_session():
    app, _ = _app()
    client = TestClient(app)
    resp = client.post("/sessions/unknown/cancel", json={"reason": "user_cancelled"})
    assert resp.status_code == 404


def test_cancel_409_already_cancelled():
    app, _ = _app()
    client = TestClient(app)
    resp = client.post("/sessions/cancelled-1/cancel", json={"reason": "user_cancelled"})
    assert resp.status_code == 409


def test_cancel_422_invalid_reason():
    app, _ = _app()
    client = TestClient(app)
    resp = client.post("/sessions/active-1/cancel", json={"reason": "not_a_reason"})
    assert resp.status_code == 422