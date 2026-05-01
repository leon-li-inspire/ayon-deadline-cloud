"""Data classes for settings across the hosts."""
from dataclasses import dataclass
import contextlib
import pyblish.api
from typing import Any, Callable
with contextlib.suppress(ImportError):
    import hou


@dataclass
class HoudiniSetting:
    """Data class for Houdini settings."""
    rop_node: hou.Node = None


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
        import hou  # type: ignore  # noqa: PGH003
        from ayon_houdini.settings import HoudiniSetting
        from deadline.houdini_submitter.python.deadline_cloud_for_houdini.submitter import (  # noqa: E501
            get_job_template_for_submission,
            get_parameter_values_for_submission,
            get_queue_parameters,
        )
        settings = HoudiniSetting()
        settings.rop_node = hou.node(instance.data.get("instance_node"))
        return SubmitterBridge(
            submitter_settings=settings,
            get_job_template_for_submission=get_job_template_for_submission,
            get_parameter_values_for_submission=get_parameter_values_for_submission,
            get_queue_parameters=get_queue_parameters,
            get_asset_references_for_submission=None,
        )

    msg = f"Unsupported host: {host_name}"
    raise NotImplementedError(msg)
