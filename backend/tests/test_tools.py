"""Agent tool sandboxing: workspace isolation, command and domain allowlists."""

from __future__ import annotations

import sys

import pytest

from tools.api_caller import APICallerTool
from tools.file_ops import FileReadTool, FileWriteTool
from tools.system_tool import SystemTool


def test_file_write_then_read_roundtrip() -> None:
    FileWriteTool(user_id="u1")._run("notes.txt", "hello workspace")
    assert "hello workspace" in FileReadTool(user_id="u1")._run("notes.txt")


def test_workspaces_are_isolated_per_user() -> None:
    FileWriteTool(user_id="u1")._run("secret.txt", "u1 only")
    assert FileReadTool(user_id="u2")._run("secret.txt") == "File not found."


@pytest.mark.parametrize("name", ["../../etc/passwd", "..", "/etc/passwd", "..\\..\\boot.ini"])
def test_file_tools_block_path_traversal(name: str) -> None:
    out = FileReadTool(user_id="u1")._run(name)
    assert "passwd" not in out or out == "File not found."
    assert "root:" not in out


def test_system_tool_rejects_commands_outside_allowlist() -> None:
    out = SystemTool(user_id="u1")._run("rm -rf /")
    assert out.startswith("Command not allowed")


@pytest.mark.parametrize(
    "command",
    ["ls /etc", "ls ../", "du -sh ../../", "ls ~", "ls C:\\Windows", "cat /etc/passwd"],
)
def test_system_tool_confined_to_workspace(command: str) -> None:
    out = SystemTool(user_id="u1")._run(command)
    assert out.startswith(("Only relative paths", "Command not allowed"))


def test_system_tool_rejects_unbalanced_quotes() -> None:
    assert SystemTool(user_id="u1")._run('echo "oops').startswith("Invalid command")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX commands")
def test_system_tool_lists_the_users_workspace() -> None:
    FileWriteTool(user_id="u1")._run("visible.txt", "x")
    out = SystemTool(user_id="u1")._run("ls")
    assert "visible.txt" in out


async def test_api_caller_blocks_non_allowlisted_domains() -> None:
    tool = APICallerTool()
    for url in ("https://evil.example.com/x", "http://169.254.169.254/latest/meta-data"):
        out = await tool._arun(url)
        assert out.startswith("Domain not whitelisted")


def test_every_agent_tool_converts_to_a_gemini_function_declaration() -> None:
    # langchain-google-genai rejects schema fields without a "type" (e.g. Optional -> anyOf),
    # which would make every chat turn fail before reaching the model.
    from langchain_google_genai._function_utils import convert_to_genai_function_declarations

    from services.llm_service import llm_service

    tools = llm_service._get_tools("u1")
    declarations = convert_to_genai_function_declarations(tools)
    assert len(declarations.function_declarations) == len(tools)


async def test_api_caller_rejects_invalid_json_body() -> None:
    out = await APICallerTool()._arun("https://httpbin.org/post", method="POST", body="{not json")
    assert out.startswith("Invalid JSON body")
