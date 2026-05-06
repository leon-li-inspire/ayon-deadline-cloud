"""Create Deadline Cloud Job."""
from __future__ import annotations

from typing import Any, Type

import nuke
from ayon_core.lib import (
    AbstractAttrDef,
    BoolDef,
    NumberDef,
    TextDef,
    EnumDef,
)
from ayon_nuke.api import NukeCreator, maintained_selection


class CreateBackdrop(NukeCreator):
    """Creator plugin to create a backdrop node representing
    Deadline Cloud Job instance.
    """  # noqa: D205
    identifier = "io.ayon.create.deadline_cloud_job"
    label = "Deadline Cloud Render Job"
    product_base_type = "deadline_cloud"
    product_type = product_base_type
    icon = "cube"

    # plugin attributes
    node_color = "0xdfea5dff"

    def create_instance_node(
        self,
        node_name: str,
        knobs: dict | None = None,
        parent: str | None = None,
        node_type: str | None = None,
        node_selection: list | None = None,
    ) -> nuke.Node:
        """Create node representing instance.

        Arguments:
            node_name (str): Name of the new node.
            knobs (dict | None): node knobs name and values
            parent (str | None): Name of the parent node.
            node_type (str | None, optional): Nuke node Class.
            node_selection (list | None): The node selection.

        Returns:
            nuke.Node: Newly created instance node.
        """
        with maintained_selection():
            op_node = nuke.createNode("NoOp")
            op_node["tile_color"].setValue(int(self.node_color, 16))
            op_node.setName(node_name)
            return op_node

    def _load_job_data(self) -> list[Type[AbstractAttrDef]]:
        """Load job template and parameters.

        Note:
            Maybe this could be moved to a collector.

        Returns:
            list[Type[AbstractAttrDef]]

        """
        from deadline.nuke_submitter.data_classes import (
            SubmitterUISettings,
        )
        from deadline.nuke_submitter.deadline_submitter_for_nuke import (
            get_job_template_for_submission,
            get_parameter_values_for_submission,
            get_queue_parameters,
        )

        settings = SubmitterUISettings()
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
                if param_def.get("userInterface", {}):
                    if param_def["userInterface"]["control"] == "CHECK_BOX":
                        out.append(
                            BoolDef(
                                label=label,
                                key=param_def["name"],
                                default=bool(value == "true"),
                            )
                        )
                    if param_def["userInterface"]["control"] == "DROPDOWN_LIST":  # noqa: E501
                        out.append(
                            EnumDef(
                                label=label,
                                key=param_def["name"],
                                items=param_def["allowedValues"],
                                default=value,
                                multiselection=True,
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
