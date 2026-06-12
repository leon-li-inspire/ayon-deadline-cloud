"""Settings for the addon."""
from typing import Any

from ayon_server.settings import BaseSettingsModel, SettingsField

DEFAULT_VALUES: dict[str, Any] = {
    "farm_id": "",
    "queue_id": "",
    "conda_packages": "",
    "conda_channels": "deadline-cloud",
    "extra_job_parameters": [],
    "publish_host_requirement_roles": ["publish"],
    "render_host_requirement_roles": ["render"],
}


class JobParameterModel(BaseSettingsModel):
    """A single custom key/value job parameter."""

    _layout = "compact"

    name: str = SettingsField(
        default="",
        title="Parameter Name",
        description=("Must match a parameterDefinition "
                     "name in the job template."),
    )
    value: str = SettingsField(
        default="",
        title="Value",
    )


class DeadlineCloudSettings(BaseSettingsModel):
    """Settings for the addon."""

    farm_id: str = SettingsField(
        default="",
        title="Farm ID",
        description=(
            "AWS Deadline Cloud farm ID (e.g. 'farm-abc123...'). "
            "Overrides the workstation's local Deadline Cloud config. "
            "Leave empty to use the workstation default."
        ),
    )

    queue_id: str = SettingsField(
        default="",
        title="Queue ID",
        description=(
            "AWS Deadline Cloud queue ID (e.g. 'queue-abc123...'). "
            "Overrides the workstation's local Deadline Cloud config. "
            "Leave empty to use the workstation default."
        ),
    )

    conda_packages: str = SettingsField(
        default="",
        title="Conda Packages",
        description=(
            "Space-separated list of Conda package specs to install on the "
            "worker (e.g. 'maya=2024 vray=6'). Overrides the Conda queue "
            "environment default. Leave empty to use the queue default."
        ),
    )

    conda_channels: str = SettingsField(
        default="deadline-cloud",
        title="Conda Channels",
        description=(
            "Space-separated list of Conda channels to search for packages "
            "(e.g. 'deadline-cloud conda-forge'). Overrides the Conda queue "
            "environment default."
        ),
    )

    extra_job_parameters: list[JobParameterModel] = SettingsField(
        default_factory=list,
        title="Extra Job Parameters",
        description=(
            "Additional key/value parameters to inject into every job "
            "submission. These override any value already present for the "
            "same parameter name. The parameter must exist in the job "
            "template's parameterDefinitions."
        ),
    )

    publish_host_requirement_roles: list[str] = SettingsField(
        default_factory=list,
        title="Publish Host Requirement Roles",
        description=(
            "When submitting job to Deadline Cloud, the publishing step "
            "will run only on machine (or fleet) that has this set as "
            "Worker Capability."
        ),
    )

    render_host_requirement_roles: list[str] = SettingsField(
        default_factory=list,
        title="render Host Requirement Roles",
        description=(
            "When submitting job to Deadline Cloud, the render step "
            "will run only on machine (or fleet) that has this set as "
            "Worker Capability."
        ),
    )
