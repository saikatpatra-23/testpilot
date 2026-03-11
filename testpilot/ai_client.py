"""Thin wrapper around the Anthropic API for TestPilot."""
import os
import anthropic


_MODEL = "claude-sonnet-4-6"


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. "
            "Export it before running: export ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic(api_key=api_key)


def generate_text(prompt: str, system: str | None = None, max_tokens: int = 4096) -> str:
    """Call Claude and return the response text."""
    kwargs: dict = {
        "model": _MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    message = _client().messages.create(**kwargs)
    return message.content[0].text
