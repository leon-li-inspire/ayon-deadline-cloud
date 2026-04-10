"""Create Deadline Cloud Job."""
from __future__ import annotations

from typing import Any, Type

from ayon_core.lib import AbstractAttrDef, BoolDef, NumberDef, UILabelDef
from ayon_maya import plugin

ojd_types_to_attr_def = {
    "PATH": UILabelDef,
    "STRING": UILabelDef,
    "INT": NumberDef,

}

class CreateDeadlineCloudJob(plugin.Creator):
    """Creator plugin for AWS Deadline Cloud Render Job."""
    identifier = "io.ayon.create.deadline_cloud_job"
    label = "Deadline Cloud Render Job"
    family = "deadline_cloud_job"

    @staticmethod
    def _load_job_data() -> list[Type[AbstractAttrDef]]:
        """Load job template and parameters.

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

        for param_def in job_template["parameterDefinitions"].items():
            if param_def["type"] in {"STRING", "PATH"}:
                out.append(
                    UILabelDef(
                        label=param_def["name"],
                        key=parameter_values_dict[param_def["name"]]
                    )
                )
            elif param_def["type"] == "INT":
                out.append(
                    NumberDef(
                        label=param_def["name"],
                        key=parameter_values_dict[param_def["name"]]
                    )
                )
        return out

    def get_instance_attr_defs(self) -> list[Type[AbstractAttrDef]]:
        """Get instance attribute definitions.

        Returns:
            list[Type[AbstractAttrDef]]: Attribute definitions.

        """
        return self._load_job_data()
