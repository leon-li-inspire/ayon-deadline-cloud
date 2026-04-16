"""Collect AWS Deadline Cloud Job Data."""
from __future__ import annotations

import dataclasses
import os
from typing import TYPE_CHECKING, Any, ClassVar, Type

import pyblish.api
from ayon_core.lib import TextDef
from ayon_core.lib.attribute_definitions import AttrDefType
from ayon_core.pipeline import KnownPublishError, get_current_host_name
from ayon_core.pipeline.publish import AYONPyblishPluginMixin, PublishError
from ayon_deadline_cloud.api import auto_detect_conda_packages
from deadline import client
from deadline.client.job_bundle.submission import AssetReferences
from deadline.maya_submitter.data_classes import RenderSubmitterUISettings
from deadline.maya_submitter.maya_render_submitter import (
    get_asset_references_for_submission,
    get_job_template_for_submission,
    get_parameter_values_for_submission,
    get_queue_parameters,
)

if TYPE_CHECKING:
    from logging import Logger

    from ayon_core.lib import AbstractAttrDef
    from ayon_core.pipeline.create import CreateContext, CreatedInstance


class CollectDeadlineCloudJobData(
    pyblish.api.InstancePlugin, AYONPyblishPluginMixin):
    """Collect job data from AWS Deadline Cloud Submitter UI."""
    label = "Collect AWS Deadline Cloud Job Data"
    order = pyblish.api.CollectorOrder + 0.1
    targets: ClassVar[list[str]] = ["local"]
    families: ClassVar[list[str]] = ["deadline_cloud"]
    settings_category = "deadline_cloud"
    log: Logger

    @classmethod
    def get_attr_defs_for_instance(
            cls,
            create_context: CreateContext,  # noqa: ARG003
            instance: CreatedInstance  # noqa: ARG003
    ) -> list[TextDef]:
        """Provide attributes to the publisher UI.

        Args:
            create_context: instance of CreateContext
            instance: CreatedInstance associated with this pyblish instance.

        Returns:
            List of attribute definitions.

        """
        return [
            TextDef(label="Extra Conda Packages",
                key="deadline_cloud_extra_conda_packages",
            )
        ]


    def process(self, instance: pyblish.api.Instance) -> None:
        """Collect job data from Deadline Maya Submitter UI.

        Args:
                instance: Pyblish instance.

        """
        ayon_settings = instance.context.data.get("project_settings", {})
        dc_settings = ayon_settings.get("deadline_cloud", {})
        settings = RenderSubmitterUISettings()
        queue_parameters: list[dict[str, Any]] = get_queue_parameters()
        asset_references = AssetReferences(
            input_filenames=set(settings.input_filenames),
            input_directories=set(settings.input_directories),
            output_directories=set(settings.output_directories),
        )

        # get attribute values
        attr_values = self.get_attr_values_from_data(instance.data)

        # this would be 'job_bundle/template.yaml'
        job_template = get_job_template_for_submission(settings)

        # job template name must be non-empty name
        if not job_template.get("name"):
            job_name = "AWS Deadline Cloud Job Data"
            if not job_template.get("name"):
                src_file: str = instance.context.data.get("currentFile", "")
                basename = os.path.basename(src_file) if src_file else ""
                job_name = basename or "AYON Deadline Cloud Job"
            job_template["name"] = job_name

        # this would be 'job_bundle/parameter_values.yaml'
        parameter_values = get_parameter_values_for_submission(
            settings, queue_parameters)

        instance_attrs = instance.data.get("creator_attributes", {})

        # parameter value mapping for in-place update
        pv_by_name: dict[str, dict] = {
            pv["name"]: pv for pv in parameter_values
        }

        # apply instance creator_attributes — only for parameters that exist
        # in the job template so we don't inject unknown parameters.
        template_param_names = {
            p["name"] for p in job_template.get("parameterDefinitions", [])
        }
        for attr_name, attr_value in instance_attrs.items():
            if attr_name not in template_param_names:
                continue
            str_value = str(attr_value) if not isinstance(
                attr_value, bool) else str(attr_value).lower()
            if attr_name in pv_by_name:
                existing = pv_by_name[attr_name]["value"]
                # Only override if the existing value is empty/falsy
                if not existing:
                    pv_by_name[attr_name]["value"] = str_value
                    self.log.debug(
                        "Overriding empty parameter %s with instance "
                        "creator_attribute value: %s", attr_name, str_value)
            else:
                pv_by_name[attr_name] = {
                    "name": attr_name, "value": str_value}
                self.log.debug(
                    "Adding missing parameter %s from instance "
                    "creator_attributes: %s", attr_name, str_value)

        # Handle conda/rez packages
        extra_conda_packages = attr_values.get(
            "deadline_cloud_extra_conda_packages")

        conda_packages_override = dc_settings.get("conda_packages", "")
        conda_channels_override = dc_settings.get("conda_channels", "")

        template_param_names = {
            p["name"] for p in job_template.get("parameterDefinitions", [])
        }

        for attr_name, attr_value in instance_attrs.items():
            if attr_name not in template_param_names:
                continue
            str_value = str(attr_value) if not isinstance(
                attr_value, bool) else str(attr_value).lower()
            if attr_name in pv_by_name:
                existing = pv_by_name[attr_name]["value"]
                # Only override if the existing value is empty/falsy
                if not existing:
                    pv_by_name[attr_name]["value"] = str_value
                    self.log.debug(
                        "Overriding empty parameter %s with instance "
                        "creator_attribute value: %s", attr_name, str_value)
            else:
                pv_by_name[attr_name] = {
                    "name": attr_name, "value": str_value}
                self.log.debug(
                    "Adding missing parameter %s from instance "
                    "creator_attributes: %s", attr_name, str_value)

        # apply AYON settings overrides for Conda parameters
        for param_name, override_value in [
            ("CondaPackages", conda_packages_override),
            ("CondaChannels", conda_channels_override),
        ]:
            if param_name not in template_param_names:
                continue
            if override_value:  # only override if explicitly set in AYON
                if param_name in pv_by_name:
                    self.log.debug(
                        "Overriding %s with AYON settings value: %s",
                        param_name, override_value)
                    pv_by_name[param_name]["value"] = override_value
                else:
                    pv_by_name[param_name] = {
                        "name": param_name, "value": override_value}

        # replicate auto-detection of conda packages from the submitter, when
        # the packages are not set.
        if "CondaPackages" in pv_by_name and not pv_by_name["CondaPackages"][
            "value"]:
            auto_conda = auto_detect_conda_packages(
                host_name=get_current_host_name(),
                job_template=job_template,
            )
            if auto_conda:
                self.log.info(
                    "Auto-detected CondaPackages from scene: %s", auto_conda)
                pv_by_name["CondaPackages"]["value"] = auto_conda

        # add any extra conda packages specified
        if extra_conda_packages and "CondaPackages" in pv_by_name:
            pv_by_name["CondaPackages"]["value"] += f" {extra_conda_packages}"

        # this would be 'job_bundle/asset_references.yaml'
        asset_refs_dict = get_asset_references_for_submission(asset_references)

        self.log.info(
            "Collected job data for AWS Deadline Cloud: ")
        instance.data["deadline_cloud_job_data"] = {
            "job_template": job_template,
            "parameter_values": parameter_values,
            "asset_references": asset_refs_dict,
        }
        self.log.info(
            "Collected job data for AWS Deadline Cloud.")

        profile_name = client.config.get_setting("defaults.aws_profile_name")
        default_farm_id = client.config.get_setting("defaults.farm_id")
        queue_id = client.config.get_setting("defaults.queue_id")
        queue_parameters: list[dict[str, Any]] = get_queue_parameters()

        # Allow AYON settings to override farm_id / queue_id.
        # Project-level settings take precedence over studio-level.
        farm_id_override = dc_settings.get("farm_id", "").strip()
        queue_id_override = dc_settings.get("queue_id", "").strip()
        if farm_id_override:
            self.log.info(
                "Overriding farm_id with AYON settings value: %s",
                farm_id_override)
            default_farm_id = farm_id_override
        if queue_id_override:
            self.log.info(
                "Overriding queue_id with AYON settings value: %s",
                queue_id_override)
            queue_id = queue_id_override

        instance.context.data["deadline_cloud_submitter_settings"] = {
            "profile_name": profile_name,
            "default_farm_id": default_farm_id,
            "queue_id": queue_id,
            "queue_parameters": queue_parameters,
            "render_settings": dataclasses.asdict(settings),
        }
        self.log.info(
            "Collected submitter settings "
            "for AWS Deadline Cloud to the context")
