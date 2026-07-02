"""Create Deadline Cloud Job."""
from __future__ import annotations

from typing import TYPE_CHECKING, Type

from ayon_vred.api import plugin

if TYPE_CHECKING:
    from ayon_core.lib import AbstractAttrDef


class CreateDeadlineCloudJob(plugin.VREDCreator):
    """Creator plugin for AWS Deadline Cloud Render Job."""
    identifier = "io.ayon.create.deadline_cloud_job"
    label = "Deadline Cloud Render Job"
    product_base_type = "deadline_cloud"
    product_type = product_base_type
    icon = "cube"

    def _load_job_data(self) -> list[Type[AbstractAttrDef]]:
        """Load job template and parameters as instance attribute definitions.

        Returns:
            list[Type[AbstractAttrDef]]

        """
        from ayon_deadline_cloud.api.create_job_common import (
            load_job_attr_defs,
        )

        return load_job_attr_defs("vred", self.log)

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
