"""Restricted shell commands, confined to the user's workspace."""

from __future__ import annotations

import asyncio
import shlex
import subprocess
from pathlib import Path

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from config import settings

ALLOWED_COMMANDS = frozenset({"ls", "pwd", "echo", "date", "whoami", "df", "du"})


class SystemCommandInput(BaseModel):
    command: str = Field(description='Command string, e.g. "ls -la" or "date"')


def _escapes_workspace(arg: str) -> bool:
    """True for arguments that could point outside the working directory."""
    return arg.startswith(("/", "\\", "~")) or ".." in Path(arg).parts or ":" in arg


class SystemTool(BaseTool):
    """Run a very small set of read-only commands inside the user's workspace."""

    name: str = "system_command"
    description: str = (
        "Run safe system commands in your workspace. "
        "Allowed commands: ls, pwd, echo, date, whoami, df, du. "
        'Input: the command string (e.g. "ls -la" or "date"). Paths must be relative.'
    )
    args_schema: type[BaseModel] = SystemCommandInput

    def __init__(self, user_id: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        workspace = Path(settings.WORKSPACE_DIR) / str(user_id)
        workspace.mkdir(parents=True, exist_ok=True)
        object.__setattr__(self, "_workspace", workspace)

    def _run(self, command: str) -> str:
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return f"Invalid command: {exc!s}"
        if not parts:
            return "Empty command."
        if parts[0] not in ALLOWED_COMMANDS:
            return f"Command not allowed. Allowed: {sorted(ALLOWED_COMMANDS)}"
        if parts[0] != "echo" and any(_escapes_workspace(arg) for arg in parts[1:]):
            return "Only relative paths inside your workspace are allowed."
        try:
            completed = subprocess.run(
                parts,
                cwd=self._workspace,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "Command timed out."
        except OSError as exc:
            return f"Command failed: {exc!s}"
        out = f"Exit code: {completed.returncode}\nOutput:\n{completed.stdout[:4000]}"
        if completed.stderr:
            out += f"\nErrors:\n{completed.stderr[:2000]}"
        return out

    async def _arun(self, command: str) -> str:
        return await asyncio.to_thread(self._run, command)
