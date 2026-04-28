"""Add publishing to the job template.

This plugin gets `instance.data["deadline_cloud_job_data"]["job_template"]`
and iterates over "steps".

First, it needs to add hostRequirement defined in the Settings to
differentiate between machines that can render and those that can publish.

See the discussion here:
    https://github.com/ynput/ayon-deadline-cloud/issues/8

Then it needs to add publish step after the render step with the dependency
on the previous rendering steps.

"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pyblish.api
from ayon_core.pipeline.publish import PublishError

if TYPE_CHECKING:
    from logging import Logger


class AddPublishingStep(pyblish.api.InstancePlugin):
    """Add publishing to the job template."""
    label = "Add Publishing Step to the Job Template"
    # make sure it runs after the data is collected
    order = pyblish.api.IntegratorOrder
    targets: ClassVar[list[str]] = ["local"]
    families: ClassVar[list[str]] = ["deadline_cloud"]
    log: Logger

    def process(self, instance: pyblish.api.Instance) -> None:
        """Process this instance.

        Args:
            instance (pyblish.api.Instance): Instance.

        Raises:
            PublishError: If job template is missing data.

        """
        ayon_settings = instance.context.data.get("project_settings", {})
        dc_settings = ayon_settings.get("deadline_cloud", {})
        render_roles: str = dc_settings.get(
            "render_host_requirement_roles", ["render"])
        publish_roles: str = dc_settings.get(
            "publish_host_requirement_roles", ["publish"])

        job_template = instance.data["deadline_cloud_job_data"]["job_template"]
        try:
            steps: list[dict] = job_template["steps"]
        except KeyError as e:
            msg = "Job template is missing 'steps' key"
            raise PublishError(msg) from e

        self._add_render_roles_to_steps(render_roles, steps)
        self._add_publishing_step(publish_roles, steps)

    def _add_render_roles_to_steps(
            self, render_roles: str, steps: list[dict]) -> None:
        """Add render roles to steps.

        This method adds `render_roles` to the render steps in the
        job template. Since there is no (easy) way to find out if the step is
        rendering or not, we assume that all steps currently are. Therefore,
        this has to run before adding publishing step.

        Args:
            render_roles (str): The render role names.
            steps (list): Steps.

        """
        # this has to be set on either the fleet or the specific
        # worker machine
        render_role_attr: dict[str, Any] = {
            "name": "attr.role",
            "anyOf": render_roles,
        }
        for step in steps:
            host_requirements = step.get("hostRequirements")
            if host_requirements is None:
                continue
            attributes: list[dict[str, Any]] = host_requirements.get(
                "attributes"
            )
            if not isinstance(attributes, list):
                continue
            if not any(
                    a.get("name") == render_role_attr["name"]
                    and a.get("anyOf") == render_role_attr["anyOf"]
                    for a in attributes
            ):
                self.log.debug("adding 'render' role to host "
                               "requirement for the step '%s'", step["name"])
                attributes.append(render_role_attr)

    @staticmethod
    def _add_publishing_step(
            publish_role: str,
            steps: list[dict]) -> None:
        """Add publishing step to the job template.

        Args:
            publish_role (str): The publishing role name.
            steps (list): Steps.

        """
        render_step_names: list[str] = [s["name"] for s in steps]
        publishing_step = {
            "name": "publish to AYON",
            "description": "Publish rendering result to AYON",
            "dependencies": [
                {"dependsOn": name} for name in render_step_names
            ],
            "hostRequirements": {
                "attributes": [
                    {"name": "attr.role", "anyOf": [publish_role]}
                ]
            },
            "script": {
                "embeddedFiles": [
                    {
                        "name": "Publish",
                        "filename": "ayon_publish.sh",
                        "type": "TEXT",
                        "data": """
#!/bin/bash
set -xeuo pipefail

echo "Running publish step for AYON Deadline Cloud addon..."
ayon addon deadline_cloud publish \
 --folder "{{Param.ayon:folderPath}}" \
 --task-name "{{Param.ayon:taskName}}" \
 --project-name "{{Param.ayon:projectName}}" \
 --user-name "{{Param.ayon:userName}}" \
 --host-name "{{Param.ayon:hostName}}" \
 "{{Param.OutputFilePath}}"
                        """
                    }
                ],
                "actions": {
                    "onRun": {
                        "command": "bash",
                        "args": [
                            "{{Task.File.Publish}}",
                        ]
                    }
                }
            }
        }

        steps.append(publishing_step)
