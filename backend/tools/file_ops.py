"""Sandboxed workspace file tools."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from config import settings

MAX_READ_BYTES = 50 * 1024


def _sanitize_filename(filename: str) -> str:
    base = Path(filename).name
    base = re.sub(r"[\x00-\x1f]", "", base)
    if base in (".", "..") or not base:
        raise ValueError("Invalid filename.")
    if ".." in base or base.startswith(("/", "\\")):
        raise ValueError("Path traversal is not allowed.")
    return base


class FileReadInput(BaseModel):
    filename: str = Field(description="Filename within the workspace (no path)")


class FileReadTool(BaseTool):
    """Read a user-scoped workspace file."""

    name: str = "file_read"
    description: str = (
        "Read a file from the workspace. Input: filename (just the filename, no path). "
        "Only files in your personal workspace are accessible."
    )
    args_schema: type[BaseModel] = FileReadInput

    def __init__(self, user_id: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.workspace = Path(settings.WORKSPACE_DIR) / str(user_id)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _run(self, filename: str) -> str:
        try:
            safe = _sanitize_filename(filename)
            path = self.workspace / safe
            if not path.exists() or not path.is_file():
                return "File not found."
            data = path.read_bytes()[:MAX_READ_BYTES]
            content = data.decode("utf-8", errors="replace")
            return f"Content of {safe}:\n{content}"
        except ValueError as exc:
            return str(exc)
        except OSError as exc:
            return f"Failed to read file: {exc!s}"

    async def _arun(self, filename: str) -> str:
        return await asyncio.to_thread(self._run, filename)


class FileWriteInput(BaseModel):
    filename: str = Field(description="Target filename in workspace")
    content: str = Field(description="Full text to write")


class FileWriteTool(BaseTool):
    """Write a user-scoped workspace file."""

    name: str = "file_write"
    description: str = (
        "Write content to a file in workspace. "
        "Provide filename and content fields. Creates or overwrites the file."
    )
    args_schema: type[BaseModel] = FileWriteInput

    def __init__(self, user_id: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.workspace = Path(settings.WORKSPACE_DIR) / str(user_id)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _run(self, filename: str, content: str) -> str:
        try:
            safe = _sanitize_filename(filename)
            path = self.workspace / safe
            written = path.write_bytes(content.encode("utf-8"))
            return f"File '{safe}' written successfully ({written} bytes)."
        except ValueError as exc:
            return str(exc)
        except OSError as exc:
            return f"Failed to write file: {exc!s}"

    async def _arun(self, filename: str, content: str) -> str:
        return await asyncio.to_thread(self._run, filename, content)
