"""Create Deadline Cloud Job."""
from __future__ import annotations

from typing import Any, Type

from ayon_core.lib import (
    AbstractAttrDef,
    BoolDef,
    EnumDef,
    NumberDef,
    TextDef,
)
from ayon_nuke.api import NukeCreator


class CreateDeadlineCloudJob(NukeCreator):
    """Creator plugin to create a backdrop node representing
    Deadline Cloud Job instance.
    """  # noqa: D205
    identifier = "deadline_cloud_job"
    label = "Deadline Cloud Render Job"
    product_base_type = "deadline_cloud"
    product_type = product_base_type
    icon = "cube"

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
                control = param_def.get("userInterface", {}).get("control", "")
                if control == "CHECK_BOX":
                    out.append(
                        BoolDef(
                            label=label,
                            key=param_def["name"],
                            default=bool(value == "true"),
                        )
                    )
                elif control == "DROPDOWN_LIST":
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

    def get_pre_create_attr_defs(self) -> list[Type[AbstractAttrDef]]:  # noqa: PLR6301
        """Get attribute definitions for pre-create step.

        Returns:
            list[Type[AbstractAttrDef]]: List of attribute definitions for
                pre-create step
        """
        return []
