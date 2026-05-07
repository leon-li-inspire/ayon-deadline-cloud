"""Create Deadline Cloud Job."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Type

from ayon_core.lib import (
    AbstractAttrDef,
    BoolDef,
    NumberDef,
    TextDef,
)
from ayon_core.pipeline.context_tools import get_current_context
from ayon_maya.api import plugin
from deadline.maya_submitter.scene import Scene
from maya import cmds

if TYPE_CHECKING:
    from ayon_core.pipeline import CreatedInstance


class CreateDeadlineCloudJob(plugin.MayaCreator):
    """Creator plugin for AWS Deadline Cloud Render Job."""
    identifier = "io.ayon.create.deadline_cloud_job"
    label = "Deadline Cloud Render Job"
    product_base_type = "deadline_cloud"
    product_type = product_base_type
    icon = "cube"

    def create(
            self,
            product_name: str,
            instance_data: dict,
            pre_create_data: dict) -> CreatedInstance:
        """Create Deadline Cloud Job.

        This is needed just to bypass default Maya validator that checks
        whether instance is empty or not. We bypass it by creating empty
        set under the instance set. This is possible because the instance
        itself is not integrated later on.

        Args:
            product_name (str): Name of the product.
            instance_data (dict): Instance data.
            pre_create_data (dict): Pre-create data.

        Returns:
            CreatedInstance: Created instance.

        """
        instance = super().create(product_name, instance_data, pre_create_data)
        instance_node = instance.get("instance_node")
        dummy_set = cmds.sets(name="empty_dummy_set", empty=True)
        cmds.sets([dummy_set], forceElement=instance_node)

        # Ensure ProjectPath and OutputFilePath are set from AYON context
        work_dir = self._get_ayon_work_dir()
        if work_dir:
            creator_attrs = instance.creator_attributes
            if not creator_attrs.get("ProjectPath"):
                creator_attrs["ProjectPath"] = Scene.project_path() or work_dir
            if not creator_attrs.get("OutputFilePath"):
                creator_attrs["OutputFilePath"] = (
                    Scene.output_path() or work_dir)

        return instance

    def _load_job_data(self) -> list[Type[AbstractAttrDef]]:
        """Load job template and parameters.

        Note:
            Maybe this could be moved to a collector.

        Returns:
            list[Type[AbstractAttrDef]]

        """
        from deadline.maya_submitter.data_classes import (
            RenderSubmitterUISettings,
        )
        from deadline.maya_submitter.maya_render_submitter import (
            get_job_template_for_submission,
            get_parameter_values_for_submission,
            get_queue_parameters,
        )

        settings = RenderSubmitterUISettings()

        # Populate project and output paths from scene settings
        work_dir = self._get_ayon_work_dir()
        if work_dir:
            settings.project_path = Scene.project_path() or work_dir
            settings.output_path = Scene.output_path() or work_dir

        queue_parameters: list[dict[str, Any]] = get_queue_parameters()

        # this would be 'job_bundle/template.yaml'
        job_template = get_job_template_for_submission(settings)
        # this would be 'job_bundle/parameter_values.yaml'
        parameter_values = get_parameter_values_for_submission(
            settings, queue_parameters)

        parameter_values_dict = {
            i["name"]: i["value"]
            for i in parameter_values
        }

        out = []

        for param_def in job_template["parameterDefinitions"]:

            try:
                value = parameter_values_dict[param_def["name"]]
            except KeyError:
                value = param_def.get("default")

            try:
                label: str = param_def["userInterface"]["label"]
            except KeyError:
                label = param_def["name"]

            self.log.debug("%s(%s): %s",
                           label, param_def["name"], value)
            if param_def["type"] in {"STRING", "PATH"}:
                if param_def["userInterface"]["control"] == "CHECK_BOX":
                    out.append(
                        BoolDef(
                            label=label,
                            key=param_def["name"],
                            default=bool(value == "true"),
                        )
                    )
                else:
                    out.append(
                        TextDef(
                            label=label,
                            key=param_def["name"],
                            default=value,
                            multiline=False,
                        )
                    )
            elif param_def["type"] == "INT":
                out.append(
                    NumberDef(
                        label=label,
                        key=param_def["name"],
                        default=value,
                    )
                )
        return out

    def get_instance_attr_defs(self) -> list[Type[AbstractAttrDef]]:
        """Get instance attribute definitions.

        Returns:
            list[Type[AbstractAttrDef]]: Attribute definitions.

        """
        return self._load_job_data()

    @staticmethod
    def _get_ayon_work_dir() -> str:
        """Get the AYON work directory for the current context.

        Returns:
            The current work directory path, or empty string on failure.

        """
        context = get_current_context()
        work_dir = context.get("work_dir", "")
        if work_dir:
            return work_dir

        # Fallback: use Maya workspace
        return cmds.workspace(query=True, rootDirectory=True) or ""
