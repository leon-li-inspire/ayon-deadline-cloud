"""Shared helpers for the per-host "Deadline Cloud Render Job" create plugins.

Every host's ``create/<host>/create_job.py`` builds the same instance attribute
definitions: it resolves the host's unified :class:`SubmitterAPI`, collects the
job template + parameter values, and converts the template's
``parameterDefinitions`` into AYON ``AbstractAttrDef`` objects. That conversion
was copy-pasted into each plugin; it lives here once instead.

Host plugins keep only their host-specific pieces (base ``Creator`` subclass,
identifier, any ``create()`` overrides, and how they seed the SubmitterAPI).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from ayon_core.lib import BoolDef, EnumDef, NumberDef, TextDef

if TYPE_CHECKING:
    import logging

    from ayon_core.lib import AbstractAttrDef
    from deadline.client.submitter_api import SubmitterAPI, SubmitterSettings


def build_attr_defs_from_template(
    job_template: dict[str, Any],
    parameter_values: list[dict[str, Any]],
    logger: logging.Logger | None = None,
) -> list[AbstractAttrDef]:
    """Convert a job template's parameterDefinitions into AYON AttrDefs.

    Args:
        job_template: The OpenJD job template dict (must contain
            ``parameterDefinitions``).
        parameter_values: The submission parameter values list
            (``{"name": ..., "value": ...}`` entries).
        logger: Optional logger for per-parameter debug output.

    Returns:
        A list of ``AbstractAttrDef`` (Bool/Enum/Text/NumberDef) to use as
        instance attribute definitions.
    """
    parameter_values_dict = {
        item["name"]: item["value"]
        for item in parameter_values
        if isinstance(item, dict) and "name" in item and "value" in item
    }

    out: list[AbstractAttrDef] = []
    for param_def in job_template["parameterDefinitions"]:
        try:
            value = parameter_values_dict[param_def["name"]]
        except KeyError:
            value = param_def.get("default")

        try:
            label: str = param_def["userInterface"]["label"]
        except KeyError:
            label = param_def["name"]

        if logger is not None:
            logger.debug("%s(%s): %s", label, param_def["name"], value)

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
                if param_def["type"] == "PATH":
                    value = Path(value).as_posix()
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


def load_job_attr_defs(
    host_name: str,
    logger: logging.Logger | None = None,
    seed_settings: Optional[
        Callable[[SubmitterAPI, SubmitterSettings], None]
    ] = None,
) -> list[AbstractAttrDef]:
    """Resolve a host's SubmitterAPI and build its instance AttrDefs.

    This is the common path used by hosts whose SubmitterAPI reads the live
    scene directly (blender, nuke, cinema4d, vred). Hosts that need to seed the
    API first (e.g. Houdini's ROP node path, Maya's work-dir defaults) can call
    :func:`build_attr_defs_from_template` directly with their own settings.

    Args:
        host_name: The AYON host name (e.g. ``"nuke"``).
        logger: Optional logger for per-parameter debug output.
        seed_settings: Optional callable ``(api, settings) -> None`` to mutate
            the freshly-collected settings before building the template.

    Returns:
        A list of ``AbstractAttrDef`` for the host's create instance.
    """
    from deadline.client.submitter_api import get_queue_parameters

    from .submitter_registry import get_submitter_api_for_host

    api = get_submitter_api_for_host(host_name)
    settings = api.get_settings()
    if seed_settings is not None:
        seed_settings(api, settings)

    queue_parameters: list[dict[str, Any]] = get_queue_parameters()
    job_template = api.get_job_template(settings)
    parameter_values = api.get_parameter_values(settings, queue_parameters)
    return build_attr_defs_from_template(
        job_template, parameter_values, logger
    )
