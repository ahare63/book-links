"""The one place the pipeline calls a language model: a command that reads a prompt on stdin."""

import json
import os
import shlex
import subprocess

# Headless Claude Code on the owner's logged-in account: no tools, no MCP servers, no user or
# project settings (so no CLAUDE.md instructions reach the judge), nothing saved to disk.
# {model} is replaced by the model a call asks for, in this command or in BOOK_LINKS_MODEL_CMD.
DEFAULT_MODEL = "haiku"
DEFAULT_COMMAND = (
    'claude -p --model {model} --tools "" --strict-mcp-config --no-session-persistence'
    ' --disable-slash-commands --setting-sources ""'
    ' --system-prompt "You assess literary scholarship questions precisely. Reply with JSON only."'
)


class ModelError(Exception):
    pass


def ask(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Send ``prompt`` to the command in BOOK_LINKS_MODEL_CMD and return what it prints."""
    template = os.environ.get("BOOK_LINKS_MODEL_CMD", DEFAULT_COMMAND)
    command = shlex.split(template.replace("{model}", model))
    try:
        result = subprocess.run(command, input=prompt, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ModelError(f"could not run {command[0]}: {error}") from error
    if result.returncode != 0:
        raise ModelError(f"{command[0]} exited {result.returncode}: {result.stderr.strip()[:200]}")
    return result.stdout


def ask_json(prompt: str, required_key: str, model: str = DEFAULT_MODEL) -> dict:
    """Ask the model and return the last JSON object in its reply that has ``required_key``."""
    reply = ask(prompt, model)
    decoder = json.JSONDecoder()
    found = None
    index = reply.find("{")
    while index != -1:
        try:
            value, length = decoder.raw_decode(reply[index:])
        except json.JSONDecodeError:
            index = reply.find("{", index + 1)
            continue
        if isinstance(value, dict) and required_key in value:
            found = value
        index = reply.find("{", index + length)
    if found is None:
        raise ModelError(f"no JSON object with '{required_key}' in the model's reply: {reply.strip()[:120]!r}")
    return found
