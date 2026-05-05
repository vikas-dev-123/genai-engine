"""Restricted local shell commands."""

from __future__ import annotations

import asyncio
import shlex
import subprocess

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

ALLOWED_COMMANDS = frozenset({"ls", "pwd", "echo", "date", "whoami", "df", "du"})


class SystemCommandInput(BaseModel):
    command: str = Field(description='Command string, e.g. "ls -la" or "date"')


class SystemTool(BaseTool):
    """Run a very small set of safe read-only style commands."""

    name: str = "system_command"
    description: str = (
        "Run safe system commands. Allowed commands: ls, pwd, echo, date, whoami, df, du. "
        'Input: the command string (e.g. "ls -la" or "date").'
    )
    args_schema: type[BaseModel] = SystemCommandInput

    def _run(self, command: str) -> str:
        try:
            parts = shlex.split(command)
            if not parts:
                return "Empty command."
            if parts[0] not in ALLOWED_COMMANDS:
                return f"Command not allowed. Allowed: {sorted(ALLOWED_COMMANDS)}"
            completed = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            out = f"Exit code: {completed.returncode}\nOutput:\n{completed.stdout}"
            if completed.stderr:
                out += f"\nErrors:\n{completed.stderr}"
            return out
        except subprocess.TimeoutExpired:
            return "Command timed out."
        except ValueError as exc:
            return f"Invalid command: {exc!s}"

    async def _arun(self, command: str) -> str:
        return await asyncio.to_thread(self._run, command)
