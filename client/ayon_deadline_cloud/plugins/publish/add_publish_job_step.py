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

import os
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
        render_roles: list[str] = dc_settings.get(
            "render_host_requirement_roles", ["render"])
        publish_roles: list[str] = dc_settings.get(
            "publish_host_requirement_roles", ["publish"])

        self.log.debug(
            "Adding render roles '%s' and "
            "publish roles '%s' to the job template",
            render_roles,
            publish_roles,
        )

        job_template = instance.data["deadline_cloud_job_data"]["jobTemplate"]
        try:
            steps: list[dict] = job_template["steps"]
        except KeyError as e:
            msg = "Job template is missing 'steps' key"
            raise PublishError(msg) from e

        self._add_render_roles_to_steps(render_roles, steps)
        self._add_publishing_step(publish_roles, steps)

    def _add_render_roles_to_steps(
            self, render_roles: list[str], steps: list[dict]) -> None:
        """Add render roles to steps.

        This method adds `render_roles` to the render steps in the
        job template. Since there is no (easy) way to find out if the step is
        rendering or not, we assume that all steps currently are. Therefore,
        this has to run before adding publishing step.

        Args:
            render_roles (list[str]): The render role names.
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
                host_requirements = step["hostRequirements"] = {}
            attributes: list[dict[str, Any]] = host_requirements.get(
                "attributes", []
            )
            if not attributes:
                host_requirements["attributes"] = attributes
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
            publish_role: list[str],
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
            "hostRequirements": {
                "attributes": [{"name": "attr.role", "anyOf": publish_role}]
            },
            "stepEnvironments": [
                {
                    "name": "CondaEnv",
                    "description": "Set to disable conda",
                    "variables": {
                        "DISABLE_CONDA_ENV": "true",
                    },
                },
                {
                    "name": "AYONEnv",
                    "description": "Set AYON env",
                    "variables": {
                        "AYON_STUDIO_BUNDLE_NAME": (
                            os.environ["AYON_STUDIO_BUNDLE_NAME"]
                        ),
                        "AYON_BUNDLE_NAME": os.environ["AYON_BUNDLE_NAME"],
                    },
                },
            ],
            "script": {
                "embeddedFiles": [
                    {
                        "name": "Publish",
                        "filename": "ayon_publish.sh",
                        "type": "TEXT",
                        "data": """
#!/bin/bash
set -xeuo pipefail

pwd

echo "File path mapping:"
cat "{{Session.PathMappingRulesFile}}"

echo "Running publish step for AYON Deadline Cloud addon..."
ayon --debug addon deadline_cloud publish \
 --folder-path "{{Param.folderPath}}" \
 --task-name "{{Param.taskName}}" \
 --project-name "{{Param.projectName}}" \
 --user-name "{{Param.userName}}" \
 --host-name "{{Param.hostName}}" \
 --product-base-type "{{Param.productBaseType}}" \
 --variant "{{Param.variant}}" \
 --source-file "{{Param.sourceFile}}" \
 --path-mapping-file "{{Session.PathMappingRulesFile}}" \
 "{{Param.OutputFilePath}}"
                        """,
                    }
                ],
                "actions": {
                    "onRun": {
                        "command": "bash",
                        "args": [
                            "{{Task.File.Publish}}",
                        ],
                    }
                },
            },
        }

        # OpenJD's JobTemplate schema requires `dependencies` to have at least
        # 1 item; only add the key when there is at least one render step to
        # depend on (a single ROP with no upstream deps yields an empty list,
        # which makes CreateJob reject the template).
        if render_step_names:
            publishing_step["dependencies"] = [
                {"dependsOn": name} for name in render_step_names
            ]

        steps.append(publishing_step)
