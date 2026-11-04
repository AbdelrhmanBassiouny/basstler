"""
A local HTTP server answering REST calls from canned responses, recording every request.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, make_server
from wsgiref.types import StartResponse

# %% what the server answers and records


@dataclass(frozen=True)
class CannedResponse:
    """
    One response the stand-in answers a request line with.
    """

    body: Any
    """
    The JSON body, ``None`` for an empty body.
    """

    status: HTTPStatus = HTTPStatus.OK
    """
    The status the response carries.
    """

    next_page_link: bool = False
    """
    Whether the response carries a ``Link`` header naming a next page.
    """


@dataclass(frozen=True)
class ReceivedRequest:
    """
    One request the stand-in received.
    """

    method: str
    """
    The HTTP method.
    """

    target: str
    """
    The path and query, as sent.
    """

    authorization: str | None
    """
    The ``Authorization`` header, ``None`` when absent.
    """

    body: Any
    """
    The decoded JSON body, ``None`` when there was none.
    """


@dataclass
class RecordingApiServer:
    """
    Answers each ``<method> <path and query>`` from :attr:`responses`, with 404 for any
    other, and records every request in :attr:`requests`.
    """

    responses: dict[str, CannedResponse] = field(default_factory=dict)
    """
    The response for each request line, keyed ``"<method> <path and query>"``.
    """

    queued_responses: dict[str, list[CannedResponse]] = field(default_factory=dict)
    """
    Responses a request line is answered with once each, oldest first, before
    :attr:`responses` answers it.
    """

    requests: list[ReceivedRequest] = field(default_factory=list)
    """
    Every request received, oldest first.
    """

    root: str = ""
    """
    The URL the server answers under, set once it is serving.
    """

    @contextmanager
    def serving(self) -> Iterator[RecordingApiServer]:
        """
        :return: This stand-in, answering on a free local port until the block ends.
        """
        server = make_server(
            "127.0.0.1", 0, self._answer, handler_class=QuietRequestHandler
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.root = f"http://127.0.0.1:{server.server_port}"
        yield self
        server.shutdown()
        server.server_close()

    def _answer(
        self, environment: dict[str, Any], start_response: StartResponse
    ) -> list[bytes]:
        """
        Record one request and answer it; the server calls this for each request.

        :param environment: The request.
        :param start_response: What the status and headers are handed to.
        :return: The body.
        """
        query = environment.get("QUERY_STRING", "")
        target = environment["PATH_INFO"] + (f"?{query}" if query else "")
        length = int(environment.get("CONTENT_LENGTH") or 0)
        raw_body = environment["wsgi.input"].read(length) if length else b""
        method = environment["REQUEST_METHOD"]
        self.requests.append(
            ReceivedRequest(
                method,
                target,
                environment.get("HTTP_AUTHORIZATION"),
                json.loads(raw_body) if raw_body else None,
            )
        )
        request_line = f"{method} {target}"
        queue = self.queued_responses.get(request_line)
        response = (
            queue.pop(0)
            if queue
            else self.responses.get(
                request_line,
                CannedResponse({"message": "Not Found"}, HTTPStatus.NOT_FOUND),
            )
        )
        payload = b"" if response.body is None else json.dumps(response.body).encode()
        headers = [("Content-Length", str(len(payload)))]
        if response.next_page_link:
            headers.append(("Link", '<https://example.invalid/2>; rel="next"'))
        start_response(f"{response.status.value} {response.status.phrase}", headers)
        return [payload]


class QuietRequestHandler(WSGIRequestHandler):
    """
    Serves requests without logging each one to the test output.
    """

    def log_message(self, message_format: str, *arguments: Any) -> None:
        return
