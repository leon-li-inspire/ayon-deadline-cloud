"""Collect AWS Deadline Cloud Job Data."""
from __future__ import annotations

import dataclasses
import os
from typing import TYPE_CHECKING, Any, ClassVar, Optional

import pyblish.api
from ayon_core.lib import TextDef
from ayon_core.pipeline import get_current_host_name
from ayon_core.pipeline.publish import AYONPyblishPluginMixin
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

    from ayon_core.pipeline.create import CreateContext, CreatedInstance


class CollectDeadlineCloudJobData(
    pyblish.api.InstancePlugin, AYONPyblishPluginMixin):
    """Collect job data from AWS Deadline Cloud Submitter UI."""
    label = "Collect AWS Deadline Cloud Job Data"
    order = pyblish.api.CollectorOrder + 0.1
    targets: ClassVar[list[str]] = ["local"]
    families: ClassVar[list[str]] = ["deadline_cloud"]
    settings_category = "deadline_cloud"

    # this could be used in the future for other hosts, but
    # we would have to move any calls with deadline.maya_submitter
    # to library.
    hosts: ClassVar[list[str]] = ["maya"]
    log: Logger

    @staticmethod
    def add_ayon_context_parameter(
            param_defs: list[dict[str, Any]],
            name: str,
            default: str,
            description: Optional[str],
    ) -> None:
        """Add an AYON context string parameter.

        Adds STRING parameter to template with AYON
        namespace.

        Args:
            param_defs: List of parameter definitions to append to.
            name: Name of the parameter (without namespace).
            default: Default value for the parameter.
            description: Optional description for the parameter.

        """
        param = {
               "name": f"ayon:{name}",
               "type": "STRING",
               "dataFlow": "OUT",
               "userInterface": {
                   "control": "HIDDEN",
               },
               "default": f"{default}",
        }
        if description is not None:
            param["description"] = description
        param_defs.append(param)

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
        """Collect job data from Deadline Submitter UI.

        Args:
                instance: Pyblish instance.

        """
        ayon_settings = instance.context.data.get("project_settings", {})
        dc_settings = ayon_settings.get("deadline_cloud", {})
        settings = RenderSubmitterUISettings()
        queue_parameters: list[dict[str, Any]] = get_queue_parameters()
        attr_values = self.get_attr_values_from_data(instance.data)

        job_template = self._build_job_template(settings, instance)
        parameter_values = get_parameter_values_for_submission(
            settings, queue_parameters)
        pv_by_name: dict[str, dict] = {
            pv["name"]: pv for pv in parameter_values
        }

        template_param_defs = job_template.get("parameterDefinitions", [])

        template_param_names = {
            p["name"] for p in job_template.get("parameterDefinitions", [])
        }
        # inject AYON context and other data used by the publishing step
        if "ayon:folderPath" not in template_param_names:
            self.add_ayon_context_parameter(
               template_param_defs,
               name="folderPath",
               default=instance.data["folderPath"],
               description="AYON folder path for this job",
            )
            template_param_names.add("ayon:folderPath")
        if "ayon:taskName" not in template_param_names:
            self.add_ayon_context_parameter(
                template_param_defs,
                name="taskName",
                default=instance.data["taskName"],
                description="AYON task for this job",
            )
            template_param_names.add("ayon:taskName")
        if "ayon:projectName" not in template_param_names:
            self.add_ayon_context_parameter(
                template_param_defs,
                name="projectName",
                default=instance.context.data["projectName"],
                description="AYON project for this job",
            )
            template_param_names.add("ayon:projectName")
        if "ayon:userName" not in template_param_names:
            self.add_ayon_context_parameter(
                template_param_defs,
                name="userName",
                default=instance.context.data.get("userName", ""),
                description="AYON user name for this job",
            )
            template_param_names.add("ayon:userName")
        if "ayon:hostName" not in template_param_names:
            self.add_ayon_context_parameter(
                template_param_defs,
                name="hostName",
                default=instance.context.data["hostName"],
                description="AYON host name for this job",
            )
            template_param_names.add("ayon:hostName")
        if "ayon:sourceFile" not in template_param_names:
            self.add_ayon_context_parameter(
                template_param_defs,
                name="sourceFile",
                default=instance.context.data.get("currentFile", ""),
                description="Source file path from the host for this job",
            )
            template_param_names.add("ayon:sourceFile")
        if "ayon:productBaseType" not in template_param_names:
            self.add_ayon_context_parameter(
                template_param_defs,
                name="productBaseType",
                default=instance.data.get("productBaseType", ""),
                description="Product base type for this job",
            )
            template_param_names.add("ayon:productBaseType")

        instance_attrs = instance.data.get("creator_attributes", {})
        self._apply_instance_attrs(
            instance_attrs, template_param_names, pv_by_name)
        self._apply_conda_overrides(
            dc_settings, template_param_names, pv_by_name)
        self._apply_auto_conda(job_template, pv_by_name)

        extra_conda_packages = attr_values.get(
            "deadline_cloud_extra_conda_packages")
        if extra_conda_packages and "CondaPackages" in pv_by_name:
            pv_by_name["CondaPackages"]["value"] += f" {extra_conda_packages}"

        asset_references = AssetReferences(
            input_filenames=set(settings.input_filenames),
            input_directories=set(settings.input_directories),
            output_directories=set(settings.output_directories),
        )
        asset_refs_dict = get_asset_references_for_submission(asset_references)

        instance.data["deadline_cloud_job_data"] = {
            "job_template": job_template,
            "parameter_values": parameter_values,
            "asset_references": asset_refs_dict,
        }
        self.log.info("Collected job data for AWS Deadline Cloud.")

        instance.context.data["deadline_cloud_submitter_settings"] = (
            self._build_submitter_settings(
                settings, dc_settings, queue_parameters)
        )
        self.log.info(
                "Collected submitter settings for "
                "AWS Deadline Cloud to the context."
            )

    @staticmethod
    def _build_job_template(
        settings: RenderSubmitterUISettings,
        instance: pyblish.api.Instance,
    ) -> dict[str, Any]:
        """Build and return the job template, ensuring it has a name.

        Args:
            settings: Render submitter UI settings.
            instance: Pyblish instance (used to derive a fallback job name).

        Returns:
            Job template dict.

        """
        job_template = get_job_template_for_submission(settings)
        if not job_template.get("name"):
            src_file: str = instance.context.data.get("currentFile", "")
            basename = os.path.basename(src_file) if src_file else ""
            job_template["name"] = basename or "AYON Deadline Cloud Job"
        return job_template

    def _apply_instance_attrs(
        self,
        instance_attrs: dict[str, Any],
        template_param_names: set[str],
        pv_by_name: dict[str, dict],
    ) -> None:
        """Apply creator_attributes to parameter values.

        Only parameters already defined in the job template are applied
        to avoid injecting unknown parameters.

        Args:
            instance_attrs: Creator attributes from the instance.
            template_param_names: Set of parameter names from the job template.
            pv_by_name: Mutable parameter-value mapping keyed by
                parameter name.

        """
        for attr_name, attr_value in instance_attrs.items():
            if attr_name not in template_param_names:
                continue
            str_value = (
                str(attr_value)
                if not isinstance(attr_value, bool)
                else str(attr_value).lower()
            )
            if attr_name in pv_by_name:
                if not pv_by_name[attr_name]["value"]:
                    pv_by_name[attr_name]["value"] = str_value
                    self.log.debug(
                        "Overriding empty parameter %s with instance "
                        "creator_attribute value: %s", attr_name, str_value)
            else:
                pv_by_name[attr_name] = {"name": attr_name, "value": str_value}
                self.log.debug(
                    "Adding missing parameter %s from instance "
                    "creator_attributes: %s", attr_name, str_value)

    def _apply_conda_overrides(
        self,
        dc_settings: dict[str, Any],
        template_param_names: set[str],
        pv_by_name: dict[str, dict],
    ) -> None:
        """Apply AYON settings overrides for Conda parameters.

        Args:
            dc_settings: Deadline Cloud AYON settings dict.
            template_param_names: Set of parameter names from the job template.
            pv_by_name: Mutable parameter-value mapping
                keyed by parameter name.

        """
        overrides = [
            ("CondaPackages", dc_settings.get("conda_packages", "")),
            ("CondaChannels", dc_settings.get("conda_channels", "")),
        ]
        for param_name, override_value in overrides:
            if param_name not in template_param_names or not override_value:
                continue
            if param_name in pv_by_name:
                self.log.debug(
                    "Overriding %s with AYON settings value: %s",
                    param_name, override_value)
                pv_by_name[param_name]["value"] = override_value
            else:
                pv_by_name[param_name] = {
                    "name": param_name, "value": override_value}

    def _apply_auto_conda(
        self,
        job_template: dict[str, Any],
        pv_by_name: dict[str, dict],
    ) -> None:
        """Auto-detect and apply CondaPackages when not already set.

        Replicates auto-detection logic from the Deadline Submitter.
        This needs to be implemented per host in api.environment.

        Args:
            job_template: Job template dict (passed to auto-detection).
            pv_by_name: Mutable parameter-value mapping
                keyed by parameter name.

        """
        if (
                "CondaPackages" not in pv_by_name
                or pv_by_name["CondaPackages"]["value"]
        ):
            return
        auto_conda = auto_detect_conda_packages(
            host_name=get_current_host_name(),
            job_template=job_template,
        )
        if auto_conda:
            self.log.info(
                "Auto-detected CondaPackages from scene: %s", auto_conda)
            pv_by_name["CondaPackages"]["value"] = auto_conda

    def _build_submitter_settings(
        self,
        settings: RenderSubmitterUISettings,
        dc_settings: dict[str, Any],
        queue_parameters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build and return the submitter settings dict for the context.

        AYON project/studio settings can override farm_id and queue_id.

        Args:
            settings: Render submitter UI settings.
            dc_settings: Deadline Cloud AYON settings dict.
            queue_parameters: Queue parameters retrieved from Deadline Cloud.

        Returns:
            Submitter settings dict.

        """
        profile_name = client.config.get_setting("defaults.aws_profile_name")
        farm_id = client.config.get_setting("defaults.farm_id")
        queue_id = client.config.get_setting("defaults.queue_id")

        farm_id_override = dc_settings.get("farm_id", "").strip()
        queue_id_override = dc_settings.get("queue_id", "").strip()
        if farm_id_override:
            self.log.info(
                "Overriding farm_id with AYON settings value: %s",
                farm_id_override)
            farm_id = farm_id_override
        if queue_id_override:
            self.log.info(
                "Overriding queue_id with AYON settings value: %s",
                queue_id_override)
            queue_id = queue_id_override

        return {
            "profile_name": profile_name,
            "default_farm_id": farm_id,
            "queue_id": queue_id,
            "queue_parameters": queue_parameters,
            "render_settings": dataclasses.asdict(settings),
        }
