"""Data classes for settings across the hosts."""
from dataclasses import dataclass
from typing import Any, Callable

import pyblish.api


@dataclass
class HoudiniSetting:
    """Data class for Houdini settings."""
    rop_node: Any = None
    input_filenames: set[str] = None
    output_directories: set[str] = None
    input_directories: set[str] = None


@dataclass
class SubmitterBridge:
    """Standardized interface for settings and functions across hosts."""
    submitter_settings: Any
    get_job_template_for_submission: Callable
    get_parameter_values_for_submission: Callable
    get_queue_parameters: Callable
    get_asset_references_for_submission: Callable


def get_submitter_bridge(
        host_name: str, instance: pyblish.api.Instance
    ) -> SubmitterBridge:
    """Get the appropriate submitter bridge for the given host.

    Args:
        host_name (str): The name of the host application.
        instance (pyblish.api.Instance): The Pyblish instance.

    Returns:
        SubmitterBridge: The submitter bridge for the specified host.

    Raises:
        NotImplementedError: If the host is not supported.
    """
    if host_name == "maya":
        from deadline.maya_submitter.data_classes import (
            RenderSubmitterUISettings,
        )
        from deadline.maya_submitter.maya_render_submitter import (
            get_asset_references_for_submission,
            get_job_template_for_submission,
            get_parameter_values_for_submission,
            get_queue_parameters,
        )
        return SubmitterBridge(
            submitter_settings=RenderSubmitterUISettings(),
            get_job_template_for_submission=get_job_template_for_submission,
            get_parameter_values_for_submission=get_parameter_values_for_submission,
            get_queue_parameters=get_queue_parameters,
            get_asset_references_for_submission=get_asset_references_for_submission,
        )

    if host_name == "houdini":
        import hou
        from deadline_cloud_for_houdini.submitter import (
            get_asset_references_for_submission,
            get_job_template_for_submission,
            get_parameter_values_for_submission,
            get_queue_parameters,
        )
        settings = HoudiniSetting()
        rop_node = hou.node(instance.data.get("instance_node"))
        settings.rop_node = rop_node
        settings.input_filenames = {
            n.unexpandedString() for n in
            rop_node.parm("input_filenames").multiParmInstances()
        }
        settings.input_directories = {
            n.unexpandedString() for n in
            rop_node.parm("input_directories").multiParmInstances()
        }
        settings.output_directories = {
            n.unexpandedString() for n in
            rop_node.parm("output_directories").multiParmInstances()
        }
        return SubmitterBridge(
            submitter_settings=settings,
            get_job_template_for_submission=get_job_template_for_submission,
            get_parameter_values_for_submission=get_parameter_values_for_submission,
            get_queue_parameters=get_queue_parameters,
            get_asset_references_for_submission=get_asset_references_for_submission,
        )

    if host_name == "nuke":
        from deadline.nuke_submitter.data_classes import (
            SubmitterUISettings,
        )
        from deadline.nuke_submitter.deadline_submitter_for_nuke import (
            get_asset_references_for_submission,
            get_job_template_for_submission,
            get_parameter_values_for_submission,
            get_queue_parameters,
        )
        return SubmitterBridge(
            submitter_settings=SubmitterUISettings(),
            get_job_template_for_submission=get_job_template_for_submission,
            get_parameter_values_for_submission=get_parameter_values_for_submission,
            get_queue_parameters=get_queue_parameters,
            get_asset_references_for_submission=get_asset_references_for_submission,
        )

    if host_name == "blender":
        from deadline_cloud_blender_submitter.template_filling import (
            get_asset_references_for_submission,
            get_job_template_for_submission,
            get_parameter_values_for_submission,
            get_queue_parameters,
            BlenderSubmitterUISettings,
        )
        return SubmitterBridge(
            submitter_settings=BlenderSubmitterUISettings(),
            get_job_template_for_submission=get_job_template_for_submission,
            get_parameter_values_for_submission=get_parameter_values_for_submission,
            get_queue_parameters=get_queue_parameters,
            get_asset_references_for_submission=get_asset_references_for_submission,
        )

    msg = f"Unsupported host: {host_name}"
    raise NotImplementedError(msg)
