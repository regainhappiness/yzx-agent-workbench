"""Runtime model options reach every agent model factory."""

from src.agents.chat_agent import ChatAgent


def test_chat_agent_passes_runtime_model_credentials(monkeypatch):
    calls = []

    def fake_get_model(**kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr("src.agents.chat_agent.get_model", fake_get_model)
    agent = ChatAgent(
        provider="deepseek",
        model="deepseek-chat",
        api_key="sk-runtime",
        base_url="https://api.deepseek.com",
        temperature=0.2,
        max_tokens=4096,
        store_type="memory",
    )

    agent.initialize()

    assert calls == [{
        "provider": "deepseek",
        "temperature": 0.2,
        "api_key": "sk-runtime",
        "base_url": "https://api.deepseek.com",
        "max_tokens": 4096,
        "model": "deepseek-chat",
    }]
