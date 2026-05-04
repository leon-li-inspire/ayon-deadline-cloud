"""Create Deadline Cloud Job."""
from __future__ import annotations

from typing import Any, Type

from ayon_core.lib import (
    AbstractAttrDef,
    BoolDef,
    NumberDef,
    TextDef,
)
from ayon_core.pipeline import CreatedInstance
from ayon_houdini.api import plugin
from ayon_deadline_cloud.api.submitter_bridge import HoudiniSetting

import hou


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
        # Lock any parameters in this list
        to_lock = ["productType", "productBaseType", "id"]
        self.lock_parameters(instance_node, to_lock)
        return instance

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
        # TODO: need to figure out how to store the data
        settings = HoudiniSetting()
        settings.rop_node = hou.node(instance.get("instance_node"))
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

    def collect_instances(self) -> None:
        """Collect instances."""
        super().collect_instances()
        collected_nodes = {
            created_instance.get("instance_node")
            for created_instance in self.create_context.instances
        }
        collected_nodes.discard(None)
        # Collect all remaining compositor output nodes
        unregistered_output_nodes = [
            node for node in hou.node("/out").children()
            if node.type().name() == "deadline_cloud"
            and node not in collected_nodes
        ]
        if not unregistered_output_nodes:
            return

        project_name = self.create_context.get_current_project_name()
        project_entity = self.create_context.get_current_project_entity()
        folder_entity = self.create_context.get_current_folder_entity()
        task_entity = self.create_context.get_current_task_entity()
        for node in unregistered_output_nodes:
            variant = node.name()
            self.log.info("Found unregistered render output node: %s",
                          variant
            )
            instance_data = self.read(node)
            product_type = instance_data.get("productType")
            if not product_type:
                product_type = self.product_base_type

            product_name = self.get_product_name(
                project_name=project_name,
                project_entity=project_entity,
                folder_entity=folder_entity,
                task_entity=task_entity,
                variant=variant,
                host_name=self.create_context.host_name,
                product_type=product_type,
            )
            instance_data.update({
                "folderPath": folder_entity["path"],
                "task": task_entity["name"],
                "productName": product_name,
                "variant": variant,
            })

            instance = CreatedInstance(
                product_base_type=self.product_base_type,
                product_type=product_type,
                product_name=product_name,
                data=instance_data,
                creator=self,
                transient_data={
                    "instance_node": node
                }
            )
            self._add_instance_to_context(instance)
