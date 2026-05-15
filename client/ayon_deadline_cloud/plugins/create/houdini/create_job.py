"""Create Deadline Cloud Job."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Type

import hou
from ayon_core.lib import (
    AbstractAttrDef,
    BoolDef,
    NumberDef,
    TextDef,
)
from ayon_core.pipeline import CreatedInstance
from ayon_deadline_cloud.api.submitter_bridge import HoudiniSetting
from ayon_houdini.api import plugin

if TYPE_CHECKING:
    import pyblish.api


class CreateDeadlineCloudJob(plugin.HoudiniCreator):
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
            CreatedInstance: The created instance.

        """
        instance_data.update({"node_type": "deadline_cloud"})
        instance = super().create(product_name, instance_data, pre_create_data)
        instance_node = hou.node(instance.get("instance_node"))
        if instance_node is None:
            self.log.warning(
                "Could not lock parameters for instance '%s' because "
                "node does not exist.",
                instance.get("instance_node"),
            )
            return instance
        # Lock any parameters in this list
        to_lock = ["productType", "productBaseType", "id"]
        self.lock_parameters(instance_node, to_lock)
        return instance

    def set_node_staging_dir(
            self,
            node: hou.Node,
            staging_dir: str,
            instance: pyblish.api.Instance,
            pre_create_data: dict
    ) -> None:
        """Set the staging directory for the given node.

        Args:
            node (hou.Node): node to set staging dir on
            staging_dir (str): staging directory path
            instance (pyblish.api.Instance): Pyblish instance
            pre_create_data (dict): pre-create data
        """

    def _load_job_data(
            self,
            instance: CreatedInstance
    ) -> list[Type[AbstractAttrDef]]:
        """Load job template and parameters.

        Note:
            Maybe this could be moved to a collector.

        Args:
            instance (CreatedInstance): Instance for which to load job data.

        Returns:
            list[Type[AbstractAttrDef]]

        """
        from deadline_cloud_for_houdini.submitter import (
            get_job_template_for_submission,
            get_parameter_values_for_submission,
            get_queue_parameters,
        )
        settings = HoudiniSetting()
        instance_node_path = instance.get("instance_node")
        rop_node = hou.node(instance_node_path) if instance_node_path else None
        if rop_node is None:
            self.log.warning(
                "Skipping Deadline Cloud job data load; instance node was not "
                "found: %s",
                instance_node_path,
            )
            return []

        settings.rop_node = rop_node
        queue_parameters: list[dict[str, Any]] = get_queue_parameters()

        # this would be 'job_bundle/template.yaml'
        job_template = get_job_template_for_submission(settings)
        # this would be 'job_bundle/parameter_values.yaml'
        parameter_values_payload = get_parameter_values_for_submission(
            settings, queue_parameters)

        if isinstance(parameter_values_payload, dict):
            parameter_values = parameter_values_payload.get("parameterValues")
        else:
            parameter_values = parameter_values_payload

        if not isinstance(parameter_values, list):
            self.log.warning(
                "Unexpected parameter values payload type: %s",
                type(parameter_values_payload).__name__,
            )
            parameter_values = []

        parameter_values_dict = {
            item["name"]: item["value"]
            for item in parameter_values
            if isinstance(item, dict)
            and "name" in item
            and "value" in item
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
                control = param_def.get("userInterface", {}).get("control", "")
                if control == "CHECK_BOX":
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

    def get_pre_create_attr_defs(self) -> list[Type[AbstractAttrDef]]:  # noqa: PLR6301
        """Get attribute definitions for pre-create step.

        Returns:
            list[Type[AbstractAttrDef]]: List of attribute definitions for
                pre-create step
        """
        return []

    def get_attr_defs_for_instance(
            self,
            instance: CreatedInstance
        ) -> list[Type[AbstractAttrDef]]:
        """Get attribute definitions for an instance.

        Args:
            instance (CreatedInstance): Instance for which to get
                attribute definitions.

        Returns:
            list[Type[AbstractAttrDef]]: List of attribute definitions.

        """
        return self._load_job_data(instance)
