"""
Fetch one upstream pull request's REST responses and print them as compact, encoded
chunks: the program a ``/upstream-reviews`` helper session runs.

A helper session has only the upstream attached, and runs no code from any other
repository, so :mod:`basstler.upstream_reviews_helper` sends it this file's source in
its prompt. That is why this module imports nothing beyond the standard library and
takes every path, pattern and field name from the JSON configuration given as its one
argument: they come from the reader and models that replay its output, so the two cannot
drift apart.

Each response keeps only the fields the models read, and the whole output is zlib-
compressed and base64-encoded, so it is small and no escaping in any transcript layer
can alter it.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from typing import Any


class FetchFailed(Exception):
    """
    Raised when ``gh`` cannot read a path.
    """


def gh(arguments: list[str]) -> str:
    """
    :param arguments: What to pass ``gh api``.
    :return: What it printed.
    :raises FetchFailed: If it exits non-zero.
    """
    completed = subprocess.run(
        ["gh", "api", *arguments], capture_output=True, text=True
    )
    if completed.returncode != 0:
        raise FetchFailed(
            f"gh api {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout


def keep_fields(value: Any, fields: set[str]) -> Any:
    """
    :param value: A parsed response, or any part of one.
    :param fields: The field names worth keeping, at any depth.
    :return: The value with every other field of every object dropped.
    """
    if isinstance(value, dict):
        return {
            name: keep_fields(entry, fields)
            for name, entry in value.items()
            if name in fields
        }
    if isinstance(value, list):
        return [keep_fields(entry, fields) for entry in value]
    return value


def fill(template: str, **values: object) -> str:
    """
    :param template: A path with ``{name}`` placeholders.
    :return: The path with each placeholder replaced.
    """
    for name, value in values.items():
        template = template.replace("{" + name + "}", str(value))
    return template


class Fetch:
    """
    One run: the responses and logs read so far, and how to read more.
    """

    def __init__(self, configuration: dict[str, Any]) -> None:
        self.configuration = configuration
        self.paths: dict[str, str] = configuration["paths"]
        self.fields = set(configuration["fields"])
        self.responses: list[dict[str, Any]] = []
        self.job_logs: list[dict[str, Any]] = []

    def get(self, path: str) -> Any:
        """
        :param path: A REST path.
        :return: Its response, unfiltered, after recording the kept fields.
        """
        body = json.loads(gh([path]))
        self.responses.append({"path": path, "body": keep_fields(body, self.fields)})
        return body

    def get_pages(self, path: str) -> list[Any]:
        """
        :param path: A paged REST path.
        :return: Every page, unfiltered, after recording the kept fields.
        """
        pages = json.loads(gh(["--paginate", "--slurp", path]))
        self.responses.append({"path": path, "body": keep_fields(pages, self.fields)})
        return pages

    def read_job_log(self, url: str | None) -> None:
        """
        Record the end of the log of the job a check's link names, if it names one.

        :param url: The check's link.
        """
        match = re.search(self.configuration["job_link"], url or "")
        if match is None:
            return
        job = int(match.group(1))
        if any(entry["job"] == job for entry in self.job_logs):
            return
        log = gh(["--allow-escape-sequences", fill(self.paths["job_log"], job=job)])
        lines = log.splitlines()[-self.configuration["log_line_limit"] :]
        self.job_logs.append({"job": job, "log": "\n".join(lines)})

    def numbers(self) -> list[int]:
        """
        :return: The pull request to read: the one asked for, or the one
            ``PullRequestSource.choose`` picks on replay out of the branch's - the fork
            owner's newest open one, else their newest - or none when they opened none.
        """
        if self.configuration["pull_request"]:
            return [self.configuration["pull_request"]]
        owned = [
            entry
            for page in self.get_pages(self.paths["pull_requests_for_head"])
            for entry in page
            if (entry["head"]["user"] or {}).get("login")
            == self.configuration["fork_owner"]
        ]
        chosen = [entry for entry in owned if entry["state"] == "open"] or owned
        return [chosen[0]["number"]] if chosen else []

    def read_pull_request(self, number: int) -> None:
        """
        Record everything the reader asks for about one pull request.

        :param number: The pull request.
        """
        pull_request = self.get(fill(self.paths["pull_request"], number=number))
        self.get_pages(fill(self.paths["reviews"], number=number))
        self.get_pages(fill(self.paths["review_comments"], number=number))
        self.get(fill(self.paths["review_threads"], number=number))
        sha = pull_request["head"]["sha"]
        runs = self.get_pages(fill(self.paths["check_runs"], sha=sha))
        statuses = self.get_pages(fill(self.paths["commit_status"], sha=sha))
        if not self.configuration["failure_logs"]:
            return
        outcomes = set(self.configuration["log_outcomes"])
        for page in runs:
            for run in page["check_runs"]:
                if run["conclusion"] in outcomes:
                    self.read_job_log(run["details_url"])
        for page in statuses:
            for status in page["statuses"]:
                if status["state"] in outcomes:
                    self.read_job_log(status["target_url"])

    def recording(self) -> dict[str, Any]:
        """:return: Everything read, as the helper module parses it."""
        return {
            "request_identifier": self.configuration["request_identifier"],
            "responses": self.responses,
            "job_logs": self.job_logs,
        }

    def output_lines(self) -> list[str]:
        """:return: The encoded recording, one marked line per chunk."""
        encoded = base64.b64encode(
            zlib.compress(
                json.dumps(self.recording(), separators=(",", ":")).encode(), 9
            )
        ).decode()
        size = self.configuration["chunk_size"]
        chunks = [
            encoded[start : start + size] for start in range(0, len(encoded), size)
        ]
        marker = self.configuration["marker"]
        return [
            f"{marker}-{index}-{len(chunks)}:{chunk}"
            for index, chunk in enumerate(chunks, 1)
        ]


def main(argv: list[str]) -> int:
    """
    Fetch, then print the output: a single chunk directly, several as files to print one
    command at a time, since a session keeps only so much of one command's output.

    :param argv: The arguments to parse: the JSON configuration, alone.
    :return: The process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configuration", type=json.loads)
    fetch = Fetch(parser.parse_args(argv).configuration)
    try:
        for number in fetch.numbers():
            fetch.read_pull_request(number)
    except FetchFailed as failure:
        print(failure, file=sys.stderr)
        return 1
    lines = fetch.output_lines()
    if len(lines) == 1:
        print(lines[0])
        return 0
    directory = Path(tempfile.mkdtemp(prefix="upstream-reviews-"))
    print(f"{len(lines)} chunks; print each with its own command:")
    for index, line in enumerate(lines, 1):
        (directory / f"chunk-{index}").write_text(line + "\n")
        print(f"cat {directory}/chunk-{index}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
