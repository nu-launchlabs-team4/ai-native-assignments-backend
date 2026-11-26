"""The language model behind the AI features, chosen by the AI_PROVIDER setting.

- claude_code: the Claude Code CLI on the developer's own login. Local development only.
- anthropic:   the Claude API with ANTHROPIC_API_KEY. For staging and the showcase.
- fake:        canned tutor-style replies. For tests and working offline.

Every AI feature calls get_llm().reply(...), so switching providers changes no feature code.
"""

import hashlib
import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# The exact model id from Anthropic's model list (no date suffix).
ANTHROPIC_MODEL = "claude-haiku-4-5"
CLAUDE_CODE_TIMEOUT_SECONDS = 90
LOCAL_ENV = "local"


class AIUnavailableError(Exception):
    """The AI couldn't answer. The message is safe to show to the student."""


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    content: str


class LanguageModel(Protocol):
    def reply(self, system: str, turns: list[Turn], max_tokens: int) -> str:
        """The model's text reply to a conversation, under a system prompt."""
        ...


class AnthropicModel:
    """The Claude API, with ANTHROPIC_API_KEY."""

    def __init__(self, api_key: str | None) -> None:
        if not api_key:
            raise AIUnavailableError("AI is not configured: set ANTHROPIC_API_KEY")
        self._client = anthropic.Anthropic(api_key=api_key)

    def reply(self, system: str, turns: list[Turn], max_tokens: int) -> str:
        try:
            response = self._client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": turn.role, "content": turn.content} for turn in turns],
            )
        except anthropic.APIError as exc:
            logger.warning("Anthropic API error: %s", type(exc).__name__)
            raise AIUnavailableError("The AI tutor is temporarily unavailable") from exc
        return "\n".join(block.text for block in response.content if block.type == "text").strip()


class ClaudeCodeModel:
    """The Claude Code CLI in headless mode, on the developer's own Claude Code login.

    A Claude Code subscription is for its owner's own use, so this only runs with
    ENV=local: never on staging or for real students. Claude Code is an agent that can
    read files and run commands, so every tool and MCP server is turned off, no settings
    or sessions are loaded or saved, and it runs in an empty folder. Student text can then
    only produce text, never act on the machine.
    """

    def __init__(self, settings: Settings) -> None:
        if settings.env != LOCAL_ENV:
            raise AIUnavailableError(
                "Claude Code is for local development only: set AI_PROVIDER=anthropic"
            )
        self._oauth_token = settings.claude_code_oauth_token

    def reply(self, system: str, turns: list[Turn], max_tokens: int) -> str:
        # The CLI takes one prompt, so earlier turns become a short transcript.
        command = [
            "claude",
            "--print",
            "--output-format",
            "json",
            "--tools",
            "",
            "--strict-mcp-config",
            "--setting-sources",
            "",
            "--no-session-persistence",
            "--system-prompt",
            system,
        ]
        try:
            with tempfile.TemporaryDirectory() as empty_dir:
                result = subprocess.run(
                    command,
                    input=_transcript(turns),
                    capture_output=True,
                    text=True,
                    timeout=CLAUDE_CODE_TIMEOUT_SECONDS,
                    cwd=empty_dir,
                    env=_cli_env(self._oauth_token),
                    check=False,
                )
        except FileNotFoundError as exc:
            raise AIUnavailableError(
                "Claude Code isn't installed: install it, or set AI_PROVIDER=fake"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AIUnavailableError("The AI tutor took too long. Try again") from exc
        return _parse_cli_result(result)


class FakeModel:
    """Canned, tutor-style replies: guiding questions, never answers. For tests and offline use."""

    REPLIES = (
        "Good start. What does your solution do with an empty input? Walk through it step by step.",
        "Which part of your approach are you least sure about? Try a small example by hand.",
        "What would change if the input were twice as long? Look at how often each line runs.",
        "Can you explain the idea behind your first step in one sentence?",
    )

    def reply(self, system: str, turns: list[Turn], max_tokens: int) -> str:
        last = turns[-1].content if turns else ""
        index = int(hashlib.sha256(last.encode()).hexdigest(), 16) % len(self.REPLIES)
        return self.REPLIES[index]


def get_llm() -> LanguageModel:
    """The model for the configured AI_PROVIDER."""
    settings = get_settings()
    if settings.ai_provider == "anthropic":
        return AnthropicModel(settings.anthropic_api_key)
    if settings.ai_provider == "fake":
        return FakeModel()
    return ClaudeCodeModel(settings)


def _cli_env(oauth_token: str | None) -> dict[str, str] | None:
    """The CLI's environment. With a token (Docker), only what it needs, so the app's own
    secrets stay out of it. Without one (a laptop), it inherits the user's environment to
    find their Claude Code login."""
    if not oauth_token:
        return None
    return {
        "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": tempfile.gettempdir(),
        "CLAUDE_CODE_OAUTH_TOKEN": oauth_token,
    }


def _transcript(turns: list[Turn]) -> str:
    if len(turns) == 1:
        return turns[0].content
    lines = [f"{'Student' if turn.role == 'user' else 'Tutor'}: {turn.content}" for turn in turns]
    return "Conversation so far:\n\n" + "\n\n".join(lines) + "\n\nReply as the tutor."


def _parse_cli_result(result: subprocess.CompletedProcess[str]) -> str:
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.warning("Claude Code returned no JSON (exit %s)", result.returncode)
        raise AIUnavailableError("The AI tutor is temporarily unavailable") from exc
    text = str(payload.get("result") or "").strip()
    if payload.get("is_error") or result.returncode != 0:
        # For example "Not logged in", which the developer can fix.
        logger.warning("Claude Code error: %s", text[:200])
        raise AIUnavailableError(f"Claude Code couldn't answer: {text or 'unknown error'}")
    return text
