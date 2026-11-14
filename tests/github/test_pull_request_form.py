"""
GitHub's pull request form, filled in from its address.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from basstler.github.pull_request_form import PullRequestForm, PullRequestFormParameter
from basstler.repository import Repository

# %% the filled-in form

FORM = PullRequestForm(
    Repository("an-owner", "a-project"),
    "main",
    "a-branch",
    "Add a workflow",
    "It marks files viewed.",
)
"""
A form for one branch with a short title and description.
"""


def test_the_form_fills_in_the_title_and_description():
    query = parse_qs(urlsplit(FORM.link.url).query)
    assert (
        query[PullRequestFormParameter.TITLE],
        query[PullRequestFormParameter.BODY],
    ) == ([FORM.title], [FORM.body])


def test_the_form_compares_the_branch_with_its_base():
    assert urlsplit(FORM.link.url).path == (
        f"/{FORM.repository.full_name}/compare/{FORM.base}...{FORM.head}"
    )
