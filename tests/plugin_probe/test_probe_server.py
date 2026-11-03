"""
Tests for the probe plugin's MCP server: it answers MCP's stdio handshake and lists one
tool, whose answer is the environment the server process received.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any

import pytest

from ..constants.paths import RepositoryLocation
from ..script_runner import BashScriptRunner

# %% the JSON-RPC exchange


class JsonRpcErrorCode(IntEnum):
    """
    The JSON-RPC 2.0 error codes the probe server answers with.
    """

    METHOD_NOT_FOUND = -32601
    """
    The request names a method the server does not implement.
    """


class ProbeMethod(StrEnum):
    """
    The MCP methods these tests send.
    """

    INITIALIZE = "initialize"
    """
    The handshake's opening request.
    """

    INITIALIZED = "notifications/initialized"
    """
    The client's notification that the handshake finished, which takes no answer.
    """

    LIST_TOOLS = "tools/list"
    """
    A request for the server's tools.
    """

    CALL_TOOL = "tools/call"
    """
    A request to run one tool.
    """

    LIST_RESOURCES = "resources/list"
    """
    A request for resources, which the probe does not serve.
    """


@dataclass
class ProbeServerSession:
    """
    One run of the probe server, fed a sequence of JSON-RPC messages on standard input.
    """

    environment: Mapping[str, str] = field(default_factory=dict)
    """
    Variables the server process runs with, standing for what Claude Code sets.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    """
    The messages sent so far, in order.
    """

    def request(self, identifier: int, method: ProbeMethod, **parameters: Any) -> None:
        """
        Queue a request, which the server answers under the same identifier.
        """
        self.messages.append(
            {"jsonrpc": "2.0", "id": identifier, "method": method, "params": parameters}
        )

    def notify(self, method: ProbeMethod) -> None:
        """
        Queue a notification, which carries no identifier and takes no answer.
        """
        self.messages.append({"jsonrpc": "2.0", "method": method})

    def answers(self, project_root: Path) -> dict[int, dict[str, Any]]:
        """
        :param project_root: The directory to run the server in.
        :return: Each answer the server wrote, keyed by the identifier it answers.
        """
        runner = BashScriptRunner(
            project_root=project_root,
            script_path=RepositoryLocation.PLUGIN_PROBE_SERVER.value,
        )
        finished = runner.run(
            standard_input="".join(
                f"{json.dumps(message)}\n" for message in self.messages
            ),
            **self.environment,
        )
        assert finished.returncode == 0, finished.stderr
        parsed = [json.loads(line) for line in finished.stdout.splitlines()]
        return {answer["id"]: answer for answer in parsed}


# %% the handshake


def test_initialize_echoes_the_protocol_version_and_offers_tools(tmp_path: Path):
    """
    The server agrees to the client's protocol version and says it serves tools.
    """
    session = ProbeServerSession()
    session.request(1, ProbeMethod.INITIALIZE, protocolVersion="2025-11-25")

    result = session.answers(tmp_path)[1]["result"]

    assert (result["protocolVersion"], result["capabilities"]) == (
        "2025-11-25",
        {"tools": {}},
    )


def test_a_notification_gets_no_answer(tmp_path: Path):
    """
    Only requests are answered; the client's initialized notification is not.
    """
    session = ProbeServerSession()
    session.request(1, ProbeMethod.INITIALIZE, protocolVersion="2025-11-25")
    session.notify(ProbeMethod.INITIALIZED)
    session.request(2, ProbeMethod.LIST_TOOLS)

    assert set(session.answers(tmp_path)) == {1, 2}


def test_an_unknown_method_is_refused_as_not_found(tmp_path: Path):
    """
    A method the probe does not serve gets JSON-RPC's method-not-found error.
    """
    session = ProbeServerSession()
    session.request(1, ProbeMethod.LIST_RESOURCES)

    assert (
        session.answers(tmp_path)[1]["error"]["code"]
        == JsonRpcErrorCode.METHOD_NOT_FOUND
    )


# %% the report tool


@pytest.mark.parametrize(
    "probe_option",
    ["default-from-manifest", 'a "quoted" \\ value\twith a tab'],
    ids=["plain", "needs-escaping"],
)
def test_the_listed_tool_reports_the_option_the_server_received(
    tmp_path: Path, probe_option: str
):
    """
    Calling the one listed tool answers with the userConfig value Claude Code put in the
    server's environment, intact through JSON escaping.
    """
    listing = ProbeServerSession()
    listing.request(1, ProbeMethod.LIST_TOOLS)
    (tool,) = listing.answers(tmp_path)[1]["result"]["tools"]

    calling = ProbeServerSession(environment={"PROBE_OPTION": probe_option})
    calling.request(1, ProbeMethod.CALL_TOOL, name=tool["name"], arguments={})
    (content,) = calling.answers(tmp_path)[1]["result"]["content"]

    assert f"mcp-server PROBE_OPTION={probe_option}" in content["text"].splitlines()


# %% what claude.ai accepts


def test_the_probe_has_no_top_level_bin_directory():
    """
    claude.ai rejects a plugin with a top-level ``bin/``, so the probe must have none to
    be uploaded at all.
    """
    assert not (RepositoryLocation.PLUGIN_PROBE / "bin").exists()
