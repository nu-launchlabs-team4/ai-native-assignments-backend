import json
import subprocess
from types import SimpleNamespace

import pytest

from app.ai import llm
from app.ai.llm import AIUnavailableError, ClaudeCodeModel, FakeModel, Turn


def settings(env: str = "local", token: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(env=env, claude_code_oauth_token=token)


def completed(payload: dict, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=json.dumps(payload), stderr=""
    )


def test_claude_code_runs_headless_with_every_tool_off(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return completed({"result": "What happens with an empty string?", "is_error": False})

    monkeypatch.setattr(llm.subprocess, "run", fake_run)

    reply = ClaudeCodeModel(settings(token="tok")).reply(
        "You are a tutor.", [Turn("user", "Is my loop right?")], max_tokens=700
    )

    assert reply == "What happens with an empty string?"
    command, kwargs = calls[0]
    assert command[:2] == ["claude", "--print"]
    assert command[command.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in command and "--no-session-persistence" in command
    assert command[command.index("--system-prompt") + 1] == "You are a tutor."
    assert kwargs["input"] == "Is my loop right?"
    # In Docker the CLI gets only its token, not the app's own secrets.
    assert kwargs["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "tok"
    assert "DATABASE_URL" not in kwargs["env"]


def test_claude_code_sends_earlier_turns_as_a_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []
    monkeypatch.setattr(
        llm.subprocess,
        "run",
        lambda command, **kw: sent.append(kw["input"]) or completed({"result": "ok"}),
    )

    ClaudeCodeModel(settings()).reply(
        "s", [Turn("user", "Hi"), Turn("assistant", "Hello"), Turn("user", "Help")], max_tokens=10
    )

    assert "Student: Hi" in sent[0] and "Tutor: Hello" in sent[0] and "Student: Help" in sent[0]


@pytest.mark.parametrize(
    ("outcome", "message"),
    [
        (completed({"result": "Not logged in", "is_error": True}), "Not logged in"),
        (subprocess.CompletedProcess([], 1, "not json", ""), "temporarily unavailable"),
    ],
    ids=["cli-error", "no-json"],
)
def test_claude_code_failures_become_clear_errors(
    monkeypatch: pytest.MonkeyPatch, outcome: subprocess.CompletedProcess, message: str
) -> None:
    monkeypatch.setattr(llm.subprocess, "run", lambda command, **kw: outcome)

    with pytest.raises(AIUnavailableError, match=message):
        ClaudeCodeModel(settings()).reply("s", [Turn("user", "Hi")], max_tokens=10)


def test_claude_code_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args, **kwargs):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(llm.subprocess, "run", missing)

    with pytest.raises(AIUnavailableError, match="isn't installed"):
        ClaudeCodeModel(settings()).reply("s", [Turn("user", "Hi")], max_tokens=10)


def test_claude_code_is_refused_outside_local_development() -> None:
    with pytest.raises(AIUnavailableError, match="local development only"):
        ClaudeCodeModel(settings(env="staging"))


def test_fake_model_always_answers_with_a_question() -> None:
    reply = FakeModel().reply("s", [Turn("user", "Just give me the answer")], max_tokens=10)

    assert reply.endswith(("?", ".")) and "?" in reply


def test_anthropic_needs_a_key() -> None:
    with pytest.raises(AIUnavailableError, match="ANTHROPIC_API_KEY"):
        llm.AnthropicModel(None)
