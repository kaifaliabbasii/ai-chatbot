"""Automatic tests for the chatbot backend.

The real AI is replaced by a fake one, so these tests need no API key,
no internet and cost nothing. Run them with:  pytest
"""
from types import SimpleNamespace

import pytest

import app as app_module


class FakeCompletions:
    def __init__(self, reply="Hello from the fake AI!"):
        self.reply = reply
        self.last_messages = None

    def create(self, **kwargs):
        self.last_messages = kwargs["messages"]
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self):
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


@pytest.fixture
def client(monkeypatch):
    app_module.app.config["TESTING"] = True
    app_module._requests.clear()
    fake = FakeClient()
    monkeypatch.setattr(app_module, "client", fake)
    test_client = app_module.app.test_client()
    test_client.fake = fake
    return test_client


def post(client, messages):
    return client.post("/chat", json={"messages": messages})


def test_home_page_loads(client):
    assert client.get("/").status_code == 200


def test_health_endpoint(client):
    data = client.get("/health").get_json()
    assert data["status"] == "ok"
    assert data["configured"] is True


def test_chat_success_and_system_prompt(client):
    res = post(client, [{"role": "user", "content": "Hi"}])
    assert res.status_code == 200
    assert res.get_json()["reply"] == "Hello from the fake AI!"
    sent = client.fake.completions.last_messages
    assert sent[0]["role"] == "system"  # system prompt is always first
    assert sent[-1] == {"role": "user", "content": "Hi"}


def test_empty_message_is_rejected(client):
    res = post(client, [{"role": "user", "content": "   "}])
    assert res.status_code == 400


def test_missing_messages_is_rejected(client):
    res = client.post("/chat", json={})
    assert res.status_code == 400


def test_too_long_message_is_rejected(client):
    long_text = "x" * (app_module.MAX_MESSAGE_CHARS + 1)
    res = post(client, [{"role": "user", "content": long_text}])
    assert res.status_code == 400


def test_history_is_trimmed(client):
    messages = []
    for i in range(30):
        messages.append({"role": "user", "content": f"question {i}"})
        messages.append({"role": "assistant", "content": f"answer {i}"})
    messages.append({"role": "user", "content": "last question"})
    res = post(client, messages)
    assert res.status_code == 200
    sent = client.fake.completions.last_messages
    assert len(sent) - 1 <= app_module.MAX_HISTORY  # minus the system prompt
    assert sent[-1]["content"] == "last question"  # newest message is kept


def test_missing_api_key(client, monkeypatch):
    monkeypatch.setattr(app_module, "client", None)
    res = post(client, [{"role": "user", "content": "Hi"}])
    assert res.status_code == 500
    assert "API_KEY" in res.get_json()["error"]


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(app_module, "RATE_LIMIT_PER_MIN", 2)
    for _ in range(2):
        assert post(client, [{"role": "user", "content": "Hi"}]).status_code == 200
    assert post(client, [{"role": "user", "content": "Hi"}]).status_code == 429


def test_unexpected_ai_error_returns_json(client):
    def boom(**kwargs):
        raise RuntimeError("boom")

    client.fake.completions.create = boom
    res = post(client, [{"role": "user", "content": "Hi"}])
    assert res.status_code == 500
    assert "error" in res.get_json()
