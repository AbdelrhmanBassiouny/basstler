"""
Setting a repository's Actions up to mark pull requests' mechanical files viewed, as
far as a command can, and naming the steps only the user can take.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated

from pydantic import Field

from basstler.class_property import classproperty
from basstler.github.client import (
    GitHubAttemptClient,
    GitHubResponse,
    HttpMethod,
    RepositoryWrite,
)
from basstler.github.repository_details import RepositoryDetails
from basstler.github.token_form import (
    FineGrainedTokenForm,
    PermissionLevel,
    RepositoryPermission,
)
from basstler.json_model import ValidatedJSONModel
from basstler.locations import ReviewTriageLocation, WorkflowLocation
from basstler.render_common import TemplatePage
from basstler.repository import BASSTLER_REPOSITORY, Repository
from basstler.review_triage.exceptions import MarkViewedWorkflowRefused
from basstler.review_triage.viewed_request import ReviewTriageSecret

# %% the REST resources the setup reads and writes


class FileWrite(RepositoryWrite):
    """
    Creates one file on a branch of a repository, as one commit.
    """

    file: Annotated[str, Field(exclude=True)]
    """
    The file's path from the repository's root.
    """

    message: str
    """
    The commit's message.
    """

    content: str
    """
    The file's content, base64-encoded as the API takes it.
    """

    branch: str
    """
    The branch the commit is made on.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.PUT

    @property
    def path(self) -> str:
        return f"{self.repository.api_path}/contents/{self.file}"


class FileUpdate(FileWrite):
    """
    Replaces one file on a branch of a repository, as one commit.
    """

    sha: str
    """
    The blob the file holds now, which the API requires to replace it.
    """


class RepositoryFile(ValidatedJSONModel):
    """
    One file of a repository, as the contents API returns it.
    """

    sha: str
    """
    The blob the file holds.
    """

    content: str
    """
    The file's content, base64-encoded with line breaks.
    """

    @property
    def text(self) -> str:
        """
        The file's content, decoded.
        """
        return base64.b64decode(self.content).decode()


class ActionsPermissions(ValidatedJSONModel):
    """
    Whether a repository runs Actions at all.
    """

    enabled: bool
    """
    Whether Actions may run in the repository.
    """


class ActionsEnabling(RepositoryWrite):
    """
    Lets a repository run Actions.
    """

    enabled: bool = True
    """
    Whether Actions may run; always on.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.PUT

    @property
    def path(self) -> str:
        return f"{self.repository.api_path}/actions/permissions"


class WorkflowState(StrEnum):
    """
    The states GitHub reports a workflow in.
    """

    ACTIVE = "active"
    """
    It runs when started.
    """


class WorkflowDetails(ValidatedJSONModel):
    """
    One workflow of a repository, as its REST resource describes it.
    """

    state: str
    """
    Whether it runs, :attr:`WorkflowState.ACTIVE`, or why not; a fork's workflows
    start out disabled.
    """


class WorkflowEnabling(RepositoryWrite):
    """
    Enables one workflow of a repository.
    """

    workflow: Annotated[WorkflowLocation, Field(exclude=True)]
    """
    The workflow.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.PUT

    @property
    def path(self) -> str:
        return f"{self.workflow_path(self.repository, self.workflow)}/enable"

    @staticmethod
    def workflow_path(repository: Repository, workflow: WorkflowLocation) -> str:
        """
        :param repository: The repository holding the workflow.
        :param workflow: The workflow.
        :return: The workflow's REST path.
        """
        return f"{repository.api_path}/actions/workflows/{workflow.name}"


# %% what each step came to


class SetupState(StrEnum):
    """
    What one step of the setup came to.
    """

    DONE = "done now"
    ALREADY_DONE = "already in place"
    REFUSED = "could not be done"
    LEFT_TO_USER = "left to you"


@dataclass(frozen=True)
class SetupStep:
    """
    One step of the setup and what it came to.
    """

    description: str
    """
    What the step sets up.
    """

    state: SetupState
    """
    What it came to.
    """

    reason: str = ""
    """
    Why it was refused or left to the user, empty otherwise.
    """


@dataclass(frozen=True)
class UserStep:
    """
    A step only the user can take, with the command and the browser steps that take
    it.
    """

    description: str
    """
    What the step does.
    """

    browser_steps: tuple[str, ...]
    """
    The step taken on github.com, one click or entry each, in order.
    """

    command: str | None = None
    """
    The command that takes it, ``None`` when GitHub offers none.
    """

    text: str | None = None
    """
    A file the step writes, shown in full, ``None`` when it writes none.
    """


# %% the setup


@dataclass(frozen=True)
class MarkViewedSetup(TemplatePage):
    """
    Sets one repository's Actions up to mark files viewed on another's pull requests.
    """

    workflow_repository: Repository
    """
    The repository whose Actions mark the files and which stores the token.
    """

    pull_request_repository: Repository | None = None
    """
    The repository the pull requests are opened on; the workflow repository's parent,
    or itself, when ``None``.
    """

    branch_or_tag: str = "main"
    """
    The basstler branch or tag the installed workflow runs.
    """

    on_every_pull_request: bool = False
    """
    Whether the workflow also runs for every pull request opened or updated on the
    workflow repository, besides when started.
    """

    steps: list[SetupStep] = field(default_factory=list)
    """
    What each step came to, in order, once :meth:`run` ran.
    """

    user_steps: list[UserStep] = field(default_factory=list)
    """
    The steps left to the user, in order, once :meth:`run` ran.
    """

    @classproperty
    def template(cls) -> str:
        return ReviewTriageLocation.MARK_VIEWED_SETUP_TEMPLATE.name

    @property
    def caller_workflow(self) -> str:
        """
        The workflow installed on the workflow repository.
        """
        return (
            self.render_named_template(
                ReviewTriageLocation.MARK_VIEWED_CALLER_TEMPLATE.name,
                basstler_repository=BASSTLER_REPOSITORY.full_name,
                reusable_workflow=WorkflowLocation.REVIEW_TRIAGE_MARK_VIEWED.as_posix(),
                branch_or_tag=self.branch_or_tag,
                token_secret=ReviewTriageSecret.VIEWER_TOKEN,
                every_pull_request=self.on_every_pull_request,
            )
            + "\n"
        )

    def run(self, client: GitHubAttemptClient) -> str:
        """
        Take every step a command can, then report them and the steps left.

        :param client: Reads and writes the workflow repository.
        :return: The report, as Markdown.
        :raises MarkViewedWorkflowRefused: If the workflow repository cannot be read.
        """
        answer = client.attempt_get(self.workflow_repository.api_path)
        if answer.failure is not None:
            raise MarkViewedWorkflowRefused(
                self.workflow_repository, answer.failure.error_message()
            )
        details = RepositoryDetails.from_json(answer.body)
        if self.on_every_pull_request and details.parent is not None:
            self.steps.append(
                SetupStep(
                    "running on every pull request",
                    SetupState.LEFT_TO_USER,
                    f"{self.workflow_repository.full_name} is a fork, which never sees "
                    f"{details.parent.full_name}'s pull requests; set the workflow up "
                    f"there with --workflow-repository {details.parent.full_name}",
                )
            )
        installed = self.install_workflow(client, details)
        self.enable_actions(client, details)
        if installed:
            self.enable_workflow(client, details)
        self.check_secret(client, details)
        return self.render_template(
            setup=self, workflow_location=WorkflowLocation.MARK_VIEWED.as_posix()
        )

    def install_workflow(
        self, client: GitHubAttemptClient, details: RepositoryDetails
    ) -> bool:
        """
        Commit the caller workflow to the default branch of a fork lacking it or
        holding another version of it.

        :param client: Reads and writes the workflow repository.
        :param details: The workflow repository.
        :return: Whether the workflow is on the default branch now.
        """
        description = (
            f"the {WorkflowLocation.MARK_VIEWED.name} workflow on "
            f"{self.workflow_repository.full_name}'s {details.default_branch}"
        )
        location = WorkflowLocation.MARK_VIEWED.as_posix()
        existing = client.attempt_get(
            f"{self.workflow_repository.api_path}/contents/{location}"
            f"?ref={details.default_branch}"
        )
        installed = (
            None
            if existing.failure is not None
            else RepositoryFile.from_json(existing.body)
        )
        if installed is not None and installed.text == self.caller_workflow:
            self.steps.append(SetupStep(description, SetupState.ALREADY_DONE))
            return True
        if not details.is_fork:
            self.leave_installation(
                description,
                f"{self.workflow_repository.full_name} is no fork, so its default "
                "branch changes only through a reviewed pull request",
                details,
                replacing=installed is not None,
            )
            return installed is not None
        commit = {
            "repository": self.workflow_repository,
            "file": location,
            "message": "Mark pull requests' mechanical files viewed from Actions\n\n"
            f"Installed by basstler {self.branch_or_tag}.",
            "content": base64.b64encode(self.caller_workflow.encode()).decode(),
            "branch": details.default_branch,
        }
        written = client.attempt_send(
            FileWrite(**commit)
            if installed is None
            else FileUpdate(**commit, sha=installed.sha)
        )
        if written.failure is not None:
            self.leave_installation(
                description,
                written.failure.error_message(),
                details,
                replacing=installed is not None,
            )
            return False
        self.steps.append(SetupStep(description, SetupState.DONE))
        return True

    def leave_installation(
        self,
        description: str,
        reason: str,
        details: RepositoryDetails,
        replacing: bool,
    ) -> None:
        """
        Record the workflow's installation as left to the user, with the file to write.

        :param description: What installing sets up.
        :param reason: Why it is left to the user.
        :param details: The workflow repository.
        :param replacing: Whether another version of the file is there already.
        """
        self.steps.append(SetupStep(description, SetupState.LEFT_TO_USER, reason))
        location = WorkflowLocation.MARK_VIEWED.as_posix()
        branch = details.default_branch
        page = (
            f"{self.workflow_repository.url}/edit/{branch}/{location}"
            if replacing
            else f"{self.workflow_repository.url}/new/{branch}?filename={location}"
        )
        self.user_steps.append(
            UserStep(
                f"{'replace' if replacing else 'add'} {location} on "
                f"{self.workflow_repository.full_name}'s {branch}",
                (
                    f"Open {page}.",
                    "Paste the workflow below as its whole content.",
                    "Commit it, through a pull request where the branch is protected.",
                ),
                text=self.caller_workflow,
            )
        )

    def enable_actions(
        self, client: GitHubAttemptClient, details: RepositoryDetails
    ) -> None:
        """
        Let a fork run Actions when it does not; for any other repository, leave that
        to the user.

        :param client: Reads and writes the workflow repository.
        :param details: The workflow repository.
        """
        description = f"Actions on {self.workflow_repository.full_name}"
        permissions = client.attempt_get(
            f"{self.workflow_repository.api_path}/actions/permissions"
        )
        if permissions.failure is not None:
            self.steps.append(
                SetupStep(
                    description,
                    SetupState.REFUSED,
                    "whether they are on could not be read: "
                    f"{permissions.failure.error_message()}",
                )
            )
            self.user_steps.append(self.actions_step(checked=False))
            return
        if ActionsPermissions.from_json(permissions.body).enabled:
            self.steps.append(SetupStep(description, SetupState.ALREADY_DONE))
            return
        if not details.is_fork:
            self.steps.append(
                SetupStep(
                    description,
                    SetupState.LEFT_TO_USER,
                    "they are off, and only a fork's settings are changed for you",
                )
            )
            self.user_steps.append(self.actions_step(checked=True))
            return
        enabled = client.attempt_send(ActionsEnabling(self.workflow_repository))
        self.record(description, enabled)
        if enabled.failure is not None:
            self.user_steps.append(self.actions_step(checked=True))

    def actions_step(self, checked: bool) -> UserStep:
        """
        :param checked: Whether Actions are known to be off.
        :return: Allowing Actions on the workflow repository.
        """
        allow = "Choose Allow all actions and reusable workflows, then click Save."
        if not checked:
            allow = f"If Actions are disabled there: {allow[0].lower()}{allow[1:]}"
        return UserStep(
            f"check that {self.workflow_repository.full_name} allows Actions"
            if not checked
            else f"allow Actions on {self.workflow_repository.full_name}",
            (f"Open {self.workflow_repository.settings_url}/actions.", allow),
        )

    def enable_workflow(
        self, client: GitHubAttemptClient, details: RepositoryDetails
    ) -> None:
        """
        Enable the installed workflow of a fork when GitHub lists it as disabled, as a
        fork's workflows start out; for any other repository, leave that to the user.

        :param client: Reads and writes the workflow repository.
        :param details: The workflow repository.
        """
        description = f"the {WorkflowLocation.MARK_VIEWED.name} workflow enabled"
        listed = client.attempt_get(
            WorkflowEnabling.workflow_path(
                self.workflow_repository, WorkflowLocation.MARK_VIEWED
            )
        )
        if listed.failure is not None:
            self.steps.append(
                SetupStep(
                    description, SetupState.REFUSED, listed.failure.error_message()
                )
            )
            return
        if WorkflowDetails.from_json(listed.body).state == WorkflowState.ACTIVE:
            self.steps.append(SetupStep(description, SetupState.ALREADY_DONE))
            return
        if not details.is_fork:
            self.steps.append(
                SetupStep(description, SetupState.LEFT_TO_USER, "it is disabled")
            )
            self.user_steps.append(
                UserStep(
                    f"enable the {WorkflowLocation.MARK_VIEWED.name} workflow",
                    (
                        f"Open {self.workflow_repository.url}/actions/workflows/"
                        f"{WorkflowLocation.MARK_VIEWED.name}.",
                        "Click Enable workflow.",
                    ),
                )
            )
            return
        self.record(
            description,
            client.attempt_send(
                WorkflowEnabling(self.workflow_repository, WorkflowLocation.MARK_VIEWED)
            ),
        )

    def check_secret(
        self, client: GitHubAttemptClient, details: RepositoryDetails
    ) -> None:
        """
        Read whether the workflow repository stores the token, leaving its creation
        and storage to the user when it does not or cannot be read.

        :param client: Reads the workflow repository.
        :param details: The workflow repository.
        """
        secret = ReviewTriageSecret.VIEWER_TOKEN
        description = f"{secret} stored on {self.workflow_repository.full_name}"
        stored = client.attempt_get(
            f"{self.workflow_repository.api_path}/actions/secrets/{secret}"
        )
        if stored.failure is None:
            self.steps.append(SetupStep(description, SetupState.ALREADY_DONE))
            return
        reason = (
            "only you can create the token"
            if stored.is_not_found
            else f"whether it is stored could not be read: "
            f"{stored.failure.error_message()}"
        )
        self.steps.append(SetupStep(description, SetupState.LEFT_TO_USER, reason))
        self.user_steps.extend(self.token_steps(details))

    def token_steps(self, details: RepositoryDetails) -> tuple[UserStep, UserStep]:
        """
        :param details: The workflow repository.
        :return: Creating the token and storing it on the workflow repository.
        """
        target = self.target_repository(details)
        form = FineGrainedTokenForm(
            "basstler mark viewed",
            f"Marks mechanical files of {target.full_name}'s pull requests viewed",
            target.owner,
            {
                RepositoryPermission.PULL_REQUESTS: PermissionLevel.WRITE,
                RepositoryPermission.CONTENTS: PermissionLevel.READ,
            },
        )
        secret = ReviewTriageSecret.VIEWER_TOKEN
        return (
            UserStep(
                f"create a token that may mark {target.full_name}'s files viewed",
                (
                    f"Open {form.url} - its name, owner and permissions are filled in.",
                    "Under Repository access, choose Only select repositories and "
                    f"select {target.full_name} alone.",
                    "Give it an expiry, click Generate token and copy it; GitHub shows "
                    "it once.",
                ),
            ),
            UserStep(
                f"store the token as {secret} on {self.workflow_repository.full_name}",
                (
                    f"Open {self.workflow_repository.new_actions_secret_url}.",
                    f"Set the name to {secret}, paste the token, then click Add secret.",
                ),
                command=(
                    f"gh secret set {secret} --repo "
                    f"{self.workflow_repository.full_name}"
                ),
            ),
        )

    def target_repository(self, details: RepositoryDetails) -> Repository:
        """
        :param details: The workflow repository.
        :return: The repository the pull requests are opened on.
        """
        if self.pull_request_repository is not None:
            return self.pull_request_repository
        if details.parent is not None:
            return Repository.parse(details.parent.full_name)
        return self.workflow_repository

    def record(self, description: str, answer: GitHubResponse) -> None:
        """
        Record a step whose write was sent.

        :param description: What the step sets up.
        :param answer: GitHub's answer to the write.
        """
        if answer.failure is None:
            self.steps.append(SetupStep(description, SetupState.DONE))
            return
        self.steps.append(
            SetupStep(description, SetupState.REFUSED, answer.failure.error_message())
        )
