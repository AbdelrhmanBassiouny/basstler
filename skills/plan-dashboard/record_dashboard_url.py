#!/usr/bin/env python3
"""
Record a published dashboard's Artifact URL into the dashboard-URL cache, resolving that
URL from the account's live Artifact listing rather than from anything the caller
remembers.

The cache exists so a later /plan-dashboard run passes ``url:`` to the Artifact
tool and updates the existing page instead of minting a second one. That only
holds while every cached URL names a page that actually exists, and the cache's
own history shows it does not survive being hand-written: across every bulk
refresh recorded on the personal-notes branch, the URLs written back named no
artifact the account had ever published. A dead entry is then passed as ``url:``
on the next run, the update cannot land on a page that isn't there, a fresh
artifact is minted, and the plan acquires a duplicate dashboard - which is the
loop this script breaks.

So the URL is never an input to be trusted here. The caller names the *key* and
the *title* it expects, and the URL is looked up in the listing, which is the
same authority every hand-correction of this cache has had to fall back on. A
URL the listing does not contain cannot be recorded at all, whatever the caller
believes about it.

Usage:
    python3 record_dashboard_url.py \\
        --key <plan-id|_index> \\
        --expected-title "<the plan's title, or the index's own title>" \\
        --listing /tmp/artifact_listing.json \\
        --cache /tmp/dashboard-urls.yaml \\
        --output /tmp/updated-dashboard-urls.yaml \\
        [--url <one of the same-titled candidates>]

``--url`` is needed only to break a tie: two artifacts sharing a title cannot be
told apart from the listing, so rather than pick one, this fails and names both.
That is the state a plan lands in once a duplicate has been minted, and which of
the pair survives is a decision for a person.

artifact_listing.json shape - one object per artifact the account owns,
transcribed from the Artifact tool's ``action: "list"`` output:
    [{"title": "<artifact title>", "url": "<artifact url>"}, ...]

The cache is patched a line at a time rather than round-tripped through a YAML
dump, for the same reason sync_manifest_status.py patches plan.yaml that way:
the header comment, key order and spacing all survive untouched, so the diff
shows the one entry that moved.

Prints a one-line JSON summary to stdout:
    {"key": ..., "url": ..., "previous_url": ..., "changed": true|false}
``changed`` is false when the cache already named the live artifact, in which
case there is nothing to push.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ARTIFACT_URL_PATTERN = re.compile(
    r"^https://claude\.ai/code/artifact/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class DashboardUrlError(ValueError):
    """
    Base class for every refusal to record a URL.
    """


class MalformedArtifactUrlError(DashboardUrlError):
    """
    Raised when a URL is not shaped like a published Artifact URL at all.
    """


class ArtifactNotPublishedError(DashboardUrlError):
    """
    Raised when no artifact in the listing carries the expected title, so there is no
    published page to record.
    """


class AmbiguousArtifactTitleError(DashboardUrlError):
    """
    Raised when several artifacts share the expected title and no ``--url`` chose
    between them.
    """


class UnlistedArtifactUrlError(DashboardUrlError):
    """
    Raised when the supplied URL is not among the artifacts carrying the
    expected title - either invented, or belonging to some other plan.
    """


@dataclass(frozen=True)
class ArtifactListingEntry:
    """
    One artifact the account owns, as reported by the Artifact tool's listing.
    """

    title: str
    """
    The artifact's title, matched against a plan's own ``title``.
    """

    url: str
    """
    The artifact's published URL.
    """


@dataclass
class UrlRecord:
    """
    The outcome of recording one key's URL.
    """

    key: str
    """
    The cache key written - a plan id, or ``_index`` for the master index.
    """

    url: str
    """
    The URL now recorded for that key.
    """

    previous_url: str | None
    """
    What the key held beforehand, or ``None`` if it had no entry.
    """

    @property
    def changed(self) -> bool:
        """
        Whether the cache moved, and so needs pushing back.
        """
        return self.previous_url != self.url

    def to_json_dict(self) -> dict[str, Any]:
        """
        Render to the plain-dict shape the calling skill expects.
        """
        return {
            "key": self.key,
            "url": self.url,
            "previous_url": self.previous_url,
            "changed": self.changed,
        }


def load_artifact_listing(
    raw_listing: list[dict[str, str]],
) -> list[ArtifactListingEntry]:
    """
    Build typed listing entries from the parsed artifact-listing JSON.

    :param raw_listing: One mapping per artifact, each with ``title`` and ``url``.
    :return: The same artifacts as typed entries, in listing order.
    """
    return [
        ArtifactListingEntry(title=entry["title"], url=entry["url"])
        for entry in raw_listing
    ]


def resolve_artifact_url(
    listing: list[ArtifactListingEntry], expected_title: str, chosen_url: str | None
) -> str:
    """
    Resolve which published artifact a key should point at.

    :param listing: Every artifact the account owns.
    :param expected_title: The title the plan's dashboard is published under.
    :param chosen_url: A caller's explicit choice, needed only when several artifacts
        share ``expected_title``.
    :raises MalformedArtifactUrlError: If ``chosen_url`` is not an Artifact URL.
    :raises ArtifactNotPublishedError: If no artifact carries ``expected_title``.
    :raises AmbiguousArtifactTitleError: If several do and ``chosen_url`` is unset.
    :raises UnlistedArtifactUrlError: If ``chosen_url`` carries a different title.
    :return: The URL to record.
    """
    if chosen_url is not None and not _ARTIFACT_URL_PATTERN.match(chosen_url):
        raise MalformedArtifactUrlError(
            f"{chosen_url!r} is not a published Artifact URL"
        )

    candidates = [entry for entry in listing if entry.title == expected_title]
    if not candidates:
        raise ArtifactNotPublishedError(
            f"no artifact is titled {expected_title!r} - "
            "publish the dashboard before recording its URL"
        )

    candidate_urls = [entry.url for entry in candidates]
    if chosen_url is None:
        if len(candidates) > 1:
            raise AmbiguousArtifactTitleError(
                f"{len(candidates)} artifacts are titled {expected_title!r} "
                f"({', '.join(candidate_urls)}) - pass --url to choose which one "
                "this key keeps"
            )
        return candidate_urls[0]

    if chosen_url not in candidate_urls:
        raise UnlistedArtifactUrlError(
            f"{chosen_url} is not among the account's artifacts titled "
            f"{expected_title!r} ({', '.join(candidate_urls)})"
        )
    return chosen_url


def apply_url_record(cache_text: str, key: str, url: str) -> tuple[str, str | None]:
    """
    Patch ``key``'s line in the cache text to ``url``, appending the key if it has no
    entry yet.

    :param cache_text: The dashboard-urls.yaml file's raw text.
    :param key: The cache key to write.
    :param url: The URL to record for it.
    :return: The patched text, and whatever ``key`` held beforehand.
    """
    key_line_pattern = re.compile(rf"^({re.escape(key)}:\s*)(\S+)\s*$")
    lines = cache_text.split("\n")
    for index, line in enumerate(lines):
        match = key_line_pattern.match(line)
        if match is None:
            continue
        previous_url = match.group(2)
        lines[index] = f"{match.group(1)}{url}"
        return "\n".join(lines), previous_url

    trailing_blank_lines = 0
    while trailing_blank_lines < len(lines) and lines[-1 - trailing_blank_lines] == "":
        trailing_blank_lines += 1
    insertion_index = len(lines) - trailing_blank_lines
    return (
        "\n".join(
            lines[:insertion_index] + [f"{key}: {url}"] + lines[insertion_index:]
        ),
        None,
    )


def main() -> int:
    """
    Parse arguments, resolve the URL, patch the cache, and print the summary.

    See the module docstring for the CLI contract.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--key", required=True, help="Cache key: a plan id, or _index for the index"
    )
    parser.add_argument(
        "--expected-title",
        required=True,
        help="The title the dashboard is published under",
    )
    parser.add_argument(
        "--listing",
        required=True,
        help='Path to a JSON file: [{"title": ..., "url": ...}, ...]',
    )
    parser.add_argument("--cache", required=True, help="Path to dashboard-urls.yaml")
    parser.add_argument(
        "--output", required=True, help="Path to write the updated cache to"
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Which same-titled artifact to keep, when more than one shares the title",
    )
    arguments = parser.parse_args()

    listing = load_artifact_listing(json.loads(Path(arguments.listing).read_text()))
    try:
        url = resolve_artifact_url(listing, arguments.expected_title, arguments.url)
    except DashboardUrlError as error:
        print(f"refusing to record a dashboard URL: {error}", file=sys.stderr)
        return 1

    cache_text = Path(arguments.cache).read_text()
    patched_text, previous_url = apply_url_record(cache_text, arguments.key, url)
    Path(arguments.output).write_text(patched_text)

    record = UrlRecord(key=arguments.key, url=url, previous_url=previous_url)
    print(json.dumps(record.to_json_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
