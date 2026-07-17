"""Create Deadline Cloud Job."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Type

from ayon_maya.api import plugin
from deadline.maya_submitter.scene import Scene
from maya import cmds

if TYPE_CHECKING:
    from ayon_core.lib import AbstractAttrDef
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
        """Load job template and parameters as instance attribute definitions.

        Returns:
            list[Type[AbstractAttrDef]]

        """
        from ayon_deadline_cloud.api.create_job_common import (
            load_job_attr_defs,
        )

        def _seed(api, settings):  # ruff:ignore[missing-type-function-argument, missing-return-type-private-function, unused-function-argument]
            # Populate project/output paths from the Maya scene + AYON workdir
            # when the submitter left them empty.
            work_dir = self._get_ayon_work_dir()
            if work_dir:
                if not settings.project_path:
                    settings.project_path = Scene.project_path() or work_dir
                if not settings.output_path:
                    settings.output_path = Scene.output_path() or work_dir

        return load_job_attr_defs("maya", self.log, seed_settings=_seed)

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
        work_dir = os.getenv("AYON_WORKDIR", "")
        if work_dir:
            return work_dir

        # Fallback: use Maya workspace
        return cmds.workspace(query=True, rootDirectory=True) or ""
