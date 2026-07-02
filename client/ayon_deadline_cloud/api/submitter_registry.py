"""Consumer-side resolution of DCC SubmitterAPI implementations.

`deadline-cloud` deliberately ships no discovery registry or factory. A
consumer always runs inside a known DCC, so this module owns the AYON-side
knowledge of which DCCs are supported and how to import their concrete
`SubmitterAPI` — and resolves one by importing it directly, on demand.

The import is deferred to call time so that a host entry does not require its
DCC modules to be importable until that host is actually used.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deadline.client.submitter_api import SubmitterAPI


# Maps each supported DCC host to the ``module.path:ClassName`` of its concrete
# SubmitterAPI. Kept here (in the consumer) rather than in deadline-cloud so
# the shared library has no dependency on the DCC submitter packages.
_SUBMITTER_API_IMPORTS: dict[str, str] = {
    "maya": "deadline.maya_submitter.submitter_api:MayaSubmitterAPI",
    "houdini": (
        "deadline_cloud_for_houdini.submitter_api:HoudiniSubmitterAPI"
    ),
    "nuke": "deadline.nuke_submitter.submitter_api:NukeSubmitterAPI",
    "blender": (
        "deadline.blender_submitter.addons.deadline_cloud_blender_submitter"
        ".submitter_api:BlenderSubmitterAPI"
    ),
    "max": "deadline.max_submitter.submitter_api:MaxSubmitterAPI",
    "cinema4d": (
        "deadline.cinema4d_submitter.submitter_api:Cinema4DSubmitterAPI"
    ),
    "unreal": "deadline.unreal_submitter.submitter_api:UnrealSubmitterAPI",
    "keyshot": "deadline.keyshot_submitter.submitter_api:KeyShotSubmitterAPI",
    "vred": "deadline.vred_submitter.submitter_api:VREDSubmitterAPI",
}

# Hosts AYON currently supports for Deadline Cloud submission.
SUPPORTED_HOSTS: list[str] = list(_SUBMITTER_API_IMPORTS)


def get_submitter_api_for_host(host_name: str) -> SubmitterAPI:
    """Import and instantiate the SubmitterAPI for a DCC host.

    The class is imported directly from its DCC package (no registry / no
    dispatch through deadline-cloud).

    Args:
        host_name: DCC identifier string (e.g. "maya", "nuke").

    Returns:
        A new SubmitterAPI instance for the host.

    Raises:
        ValueError: If the host has no SubmitterAPI mapping.
    """
    entry = _SUBMITTER_API_IMPORTS.get(host_name)
    if entry is None:
        msg = (
            f"No SubmitterAPI mapping for host '{host_name}'. "
            f"Supported: {SUPPORTED_HOSTS}"
        )
        raise ValueError(msg)

    module_path, class_name = entry.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()
