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
            steps: dict = job_template["steps"]
        except KeyError as e:
            msg = "Job template is missing 'steps' key"
            raise PublishError(msg) from e

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

