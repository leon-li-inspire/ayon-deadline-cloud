"""Submitter bridge across all DCC hosts.

This bridges AYON's publishing plugins to the unified ``SubmitterAPI`` defined
in ``deadline-cloud``. A single :class:`SubmitterBridge` works for every DCC
that registers a ``SubmitterAPI`` (see
:mod:`ayon_deadline_cloud.api.submitter_registry`), so no per-host bridge code
is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

from deadline.client.submitter_api import get_queue_parameters

from .submitter_registry import get_submitter_api_for_host

if TYPE_CHECKING:
    from deadline.client.job_bundle.submission import AssetReferences


@dataclass
class SubmitterBridge:
    """Standardized interface for settings and functions across hosts."""

    submitter_settings: Any
    get_job_template_for_submission: Callable
    get_parameter_values_for_submission: Callable
    get_queue_parameters: Callable
    get_asset_references_for_submission: Callable


def _unified_submitter_bridge(
    host_name: str,
    instance_node: Optional[str] = None,
) -> SubmitterBridge:
    """Build a SubmitterBridge backed by the unified SubmitterAPI.

    Works for any DCC with a SubmitterAPI. The concrete class is imported
    directly (no registry / no dispatch through deadline-cloud). The returned
    bridge keeps the same call shape the publishing plugins already expect.

    Args:
        host_name: The name of the host application (e.g. "maya").
        instance_node: Optional host node path identifying the instance being
            submitted. Most DCCs resolve everything from the live scene and
            ignore this, but some (e.g. Houdini) resolve their settings and job
            template from a specific node (its ROP), so the publish side must
            seed it before ``get_settings()`` — the same way the create plugin
            does. When the API exposes a ``_rop_node_path`` slot and a node is
            provided, it is seeded here.

    Returns:
        A SubmitterBridge delegating to the host's SubmitterAPI.
    """
    api = get_submitter_api_for_host(host_name)
    # Host-specific node seeding: Houdini's SubmitterAPI derives its settings
    # and job template from a ROP node path. The create plugin seeds this at
    # create time; the publish bridge must do the same, otherwise
    # get_settings()/get_job_template() raise "Cannot find ROP node at path: ".
    if instance_node and hasattr(api, "_rop_node_path"):
        api._rop_node_path = instance_node  # noqa: SLF001
    settings = api.get_settings()

    def _job_template(
        _settings: object,
        host_requirements: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return api.get_job_template(_settings, host_requirements)

    def _parameter_values(
        _settings: object,
        queue_parameters: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        return api.get_parameter_values(_settings, queue_parameters or [])

    def _queue_parameters(
        farm_id: Optional[str] = None,
        queue_id: Optional[str] = None,
        initial_values: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        return get_queue_parameters(
            farm_id=farm_id,
            queue_id=queue_id,
            initial_values=initial_values,
        )

    def _asset_references(
        _asset_references: Optional[AssetReferences] = None,
    ) -> dict[str, Any]:
        return api.get_asset_references(settings)

    return SubmitterBridge(
        submitter_settings=settings,
        get_job_template_for_submission=_job_template,
        get_parameter_values_for_submission=_parameter_values,
        get_queue_parameters=_queue_parameters,
        get_asset_references_for_submission=_asset_references,
    )


def get_submitter_bridge(
    host_name: str,
    instance_node: Optional[str] = None,
) -> SubmitterBridge:
    """Get the submitter bridge for the given host.

    Backed by the unified SubmitterAPI, which supports every DCC that
    registers one (see :mod:`ayon_deadline_cloud.api.submitter_registry`).

    Args:
        host_name (str): The name of the host application.
        instance_node (Optional[str]): Optional host node path identifying the
            instance being submitted. Forwarded to the SubmitterAPI for hosts
            (e.g. Houdini) that resolve their data from a specific node.

    Returns:
        SubmitterBridge: The submitter bridge for the specified host.
    """
    return _unified_submitter_bridge(host_name, instance_node=instance_node)
