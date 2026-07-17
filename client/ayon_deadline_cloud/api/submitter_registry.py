"""Consumer-side resolution of DCC ``BaseSubmitter`` implementations.

`deadline-cloud` deliberately ships no discovery registry or factory. A
consumer always runs inside a known DCC, so this module owns the AYON-side
knowledge of which DCCs are supported and how to import their concrete
``BaseSubmitter`` subclass — and resolves one by importing it directly, on
demand.

The import is deferred to call time so that a host entry does not require its
DCC modules to be importable until that host is actually used.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deadline.client.api import BaseSubmitter


# Maps each supported DCC host to one or more ``module.path:ClassName``
# candidate import specs for its concrete ``BaseSubmitter`` subclass, tried in
# order. Kept here (in the consumer) rather than in deadline-cloud so the
# shared library has no dependency on the DCC submitter packages.
#
# Most DCCs expose a single stable import name. Blender is the exception: it
# ships as a Blender *addon* whose modules are importable under
# ``deadline_cloud_blender_submitter`` when installed the normal way, while
# the deep ``deadline.blender_submitter.addons.…`` path only resolves in the
# source / wheel layout. List both so resolution works in either environment.
#
# deadline-cloud-for-blender also renamed submitter_api -> submitter and
# BlenderSubmitterAPI -> BlenderSubmitter (aligning with the BaseSubmitter
# rename). Prefer the new module/class; fall back to the old names so an older
# blender submitter install still resolves. Cross with the two layouts above,
# giving four candidates tried new-first, addon-before-source.
_BLENDER_ADDON_API = (
    "deadline_cloud_blender_submitter.submitter:BlenderSubmitter"
)
_BLENDER_SOURCE_API = (
    "deadline.blender_submitter.addons.deadline_cloud_blender_submitter"
    ".submitter:BlenderSubmitter"
)
_BLENDER_ADDON_API_LEGACY = (
    "deadline_cloud_blender_submitter.submitter_api:BlenderSubmitterAPI"
)
_BLENDER_SOURCE_API_LEGACY = (
    "deadline.blender_submitter.addons.deadline_cloud_blender_submitter"
    ".submitter_api:BlenderSubmitterAPI"
)
_SUBMITTER_IMPORTS: dict[str, tuple[str, ...]] = {
    # deadline-cloud-for-maya renamed submitter_api -> submitter and
    # MayaSubmitterAPI -> MayaSubmitter. Prefer the new name; fall back to the
    # old one so an older maya submitter install still resolves.
    "maya": (
        "deadline.maya_submitter.submitter:MayaSubmitter",
        "deadline.maya_submitter.submitter_api:MayaSubmitterAPI",
    ),
    # deadline-cloud-for-houdini renamed submitter_api -> submitter (the
    # engine) and its old submitter.py -> gui_submitter.py (the native GUI
    # callbacks), and HoudiniSubmitterAPI -> HoudiniSubmitter (aligning with
    # the BaseSubmitter rename). Prefer the new module/class; keep the legacy
    # module/class specs as fallbacks so an older install still resolves.
    "houdini": (
        "deadline_cloud_for_houdini.submitter:HoudiniSubmitter",
        "deadline_cloud_for_houdini.submitter_api:HoudiniSubmitter",
        "deadline_cloud_for_houdini.submitter_api:HoudiniSubmitterAPI",
    ),
    # deadline-cloud-for-nuke renamed submitter_api -> submitter and
    # NukeSubmitterAPI -> NukeSubmitter (aligning with the BaseSubmitter
    # rename); the old submitter_api module was removed. Prefer the new
    # module/class; keep the legacy spec as a fallback for older installs.
    "nuke": (
        "deadline.nuke_submitter.submitter:NukeSubmitter",
        "deadline.nuke_submitter.submitter_api:NukeSubmitterAPI",
    ),
    "blender": (
        # New name — addon install (real Blender): addon dir is on sys.path.
        _BLENDER_ADDON_API,
        # New name — source / wheel layout: under the deadline namespace.
        _BLENDER_SOURCE_API,
        # Legacy name fallbacks (pre-rename installs), same layout order.
        _BLENDER_ADDON_API_LEGACY,
        _BLENDER_SOURCE_API_LEGACY,
    ),
}

# Hosts AYON currently supports for Deadline Cloud submission.
SUPPORTED_HOSTS: list[str] = list(_SUBMITTER_IMPORTS)


def get_submitter_for_host(host_name: str) -> BaseSubmitter:
    """Import and instantiate the ``BaseSubmitter`` subclass for a DCC host.

    The class is imported directly from its DCC package (no registry / no
    dispatch through deadline-cloud). When a host declares multiple candidate
    import specs, they are tried in order and the first importable one wins.

    Args:
        host_name: DCC identifier string (e.g. "maya", "nuke").

    Returns:
        A new ``BaseSubmitter`` subclass instance for the host.

    Raises:
        ValueError: If the host has no submitter mapping.
        ModuleNotFoundError: If none of the host's candidate specs resolve.
    """
    candidates = _SUBMITTER_IMPORTS.get(host_name)
    if candidates is None:
        msg = (
            f"No submitter mapping for host '{host_name}'. "
            f"Supported: {SUPPORTED_HOSTS}"
        )
        raise ValueError(msg)

    last_error: ModuleNotFoundError | None = None
    for entry in candidates:
        module_path, class_name = entry.rsplit(":", 1)
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            last_error = exc
            continue
        return getattr(module, class_name)()

    tried = ", ".join(spec.split(":", 1)[0] for spec in candidates)
    msg = (
        f"Could not import the submitter for host '{host_name}'. "
        f"Tried: {tried}"
    )
    raise ModuleNotFoundError(msg) from last_error
