"""
The names every site page's live-state script spells GitHub's pull requests with.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from basstler.github.pull_request_record import (
    PullRequestField,
)
from basstler.github.pull_request_state import LiveState, PullRequestState
from basstler.github.tooling_labels import GitHubLabel
from basstler.plan_site.live_state_display import LiveStateDisplay

# %% the vocabulary


@dataclass(frozen=True)
class LiveStateVocabulary:
    """
    The enumerations a site page's script reads a pull request's live state with, so the
    browser classifies it as the build does.
    """

    live_state: type[LiveState] = field(default=LiveState, init=False)
    """
    The states a pull request is shown in.
    """

    live_state_display: LiveStateDisplay = field(
        default_factory=LiveStateDisplay, init=False
    )
    """
    How the script shows and counts each live state.
    """

    github_label: type[GitHubLabel] = field(default=GitHubLabel, init=False)
    """
    The labels the script reads off a pull request.
    """

    pull_request_field: type[PullRequestField] = field(
        default=PullRequestField, init=False
    )
    """
    The fields the script reads off GitHub's pull request.
    """

    pull_request_state: type[PullRequestState] = field(
        default=PullRequestState, init=False
    )
    """
    The states GitHub gives a pull request.
    """
