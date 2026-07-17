"""Tools for handling conda/rez packages."""
from __future__ import annotations

import importlib
from typing import Any

# Candidate module paths for the Blender submitter's ``_version`` module.
# Blender ships as an addon importable under
# ``deadline_cloud_blender_submitter`` when installed the normal way; the deep
# ``deadline.blender_submitter.addons.…`` path only resolves in the source /
# wheel layout. Try both. Keep in sync with
# submitter_registry._SUBMITTER_IMPORTS["blender"].
_BLENDER_VERSION_ADDON = "deadline_cloud_blender_submitter._version"
_BLENDER_VERSION_SOURCE = (
    "deadline.blender_submitter.addons"
    ".deadline_cloud_blender_submitter._version"
)
_BLENDER_VERSION_MODULES: tuple[str, ...] = (
    _BLENDER_VERSION_ADDON,
    _BLENDER_VERSION_SOURCE,
)


def _import_blender_adaptor_version_tuple() -> tuple[int, ...]:
    """Import the Blender submitter ``version_tuple``.

    Tries each candidate layout in ``_BLENDER_VERSION_MODULES`` in order and
    returns the first that resolves.

    Returns:
        The adaptor ``version_tuple``.

    Raises:
        ModuleNotFoundError: If no candidate module resolves.

    """
    last_error: ModuleNotFoundError | None = None
    for module_path in _BLENDER_VERSION_MODULES:
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            last_error = exc
            continue
        return module.version_tuple

    tried = ", ".join(_BLENDER_VERSION_MODULES)
    msg = (
        "Could not import the Blender submitter _version module. "
        f"Tried: {tried}"
    )
    raise ModuleNotFoundError(msg) from last_error


def _extract_renderers(job_template: dict[str, Any]) -> set[str]:
    """Extract renderers for a given job template.

    Args:
        job_template: The job template dict (already generated).

    Returns:
        A set of renderer names found in the job template.

    """
    renderers: set[str] = set()
    for step in job_template.get("steps", []):
        for env in step.get("stepEnvironments", []):
            for ef in env.get("script", {}).get("embeddedFiles", []):
                data_str = ef.get("data", "")
                for line in data_str.splitlines():
                    line = line.strip()  # ruff:ignore[redefined-loop-name]
                    if not line.startswith("renderer:"):
                        continue
                    renderer = line.split(":", 1)[1].strip()
                    if renderer:
                        renderers.add(renderer)
    return renderers


class HostCondaPackages:
    """Implementation of conda package detection for different hosts.

    Each host gets its own conda package list.
    """
    def __init__(self, job_template: dict[str, Any]) -> None:
        """Initialize the conda package detection class.

        Args:
            job_template: The job template dict (already generated).

        """
        self._job_template = job_template

    def _get_conda_pkgs_for_maya(self) -> list[str]:
        """Get a list of conda packages for Maya.

        Returns:
            A list of conda packages for Maya

        """
        from deadline.maya_submitter._version import (  # ruff:ignore[import-private-name]
            version_tuple as adaptor_version_tuple,
        )

        packages: list[str] = []
        try:
            import maya.cmds  # ty:ignore[unresolved-import]

            maya_version = maya.cmds.about(version=True)
        except Exception:  # ruff:ignore[blind-except]
            maya_version = None

        # note: this is used to get the version of the adaptor, which is
        # not necessarily the same as the Maya version. Sometimes it happens
        # that the version in dev build is set incorrectly? to 0.0 and then
        # the submitted jobs will fail because that conda package can't be
        # found in the default conda channel. This simple fix will release
        # the version constrain in that case.
        adaptor_version = ".".join(str(v) for v in adaptor_version_tuple[:2])
        adaptor_version = f"={adaptor_version}.*"
        if adaptor_version_tuple[0] == 0 and adaptor_version_tuple[1] == 0:
            adaptor_version = ""
        packages.extend(
            (
                f"maya={maya_version}.*",
                f"maya-openjd{adaptor_version}",
            ))

        # handle maya renderers
        renderers = _extract_renderers(self._job_template)
        if "arnold" in renderers:
            packages.append("maya-mtoa")
        if "vray" in renderers:
            packages.append("maya-vray")
        if "redshift" in renderers:
            packages.append("maya-redshift")

        return packages

    def _get_conda_pkgs_for_houdini(self) -> list[str]:  # ruff:ignore[no-self-use]
        """Get a list of conda packages for Houdini.

        Returns:
            A list of conda packages for Houdini

        """
        from deadline_cloud_for_houdini._version import (  # ruff:ignore[import-private-name]
            version_tuple as adaptor_version_tuple,
        )

        packages: list[str] = []
        try:
            import hou  # ty:ignore[unresolved-import]

            houdini_version = hou.applicationVersionString().rsplit(".", 1)[0]
        except Exception:  # ruff:ignore[blind-except]
            houdini_version = None

        # note: this is used to get the version of the adaptor, which is
        # not necessarily the same as the Houdini version. Sometimes it happens
        # that the version in dev build is set incorrectly? to 0.0 and then
        # the submitted jobs will fail because that conda package can't be
        # found in the default conda channel. This simple fix will release
        # the version constrain in that case.
        adaptor_version = ".".join(str(v) for v in adaptor_version_tuple[:2])
        adaptor_version = f"={adaptor_version}.*"
        if adaptor_version_tuple[0] == 0 and adaptor_version_tuple[1] == 0:
            adaptor_version = ""
        packages.extend(
            (
                f"houdini={houdini_version}.*",
                f"houdini-openjd{adaptor_version}",
            ))

        return packages

    def _get_conda_pkgs_for_blender(self) -> list[str]:  # ruff:ignore[no-self-use]
        """Get a list of conda packages for Blender.

        Returns:
            A list of conda packages for Blender

        """
        adaptor_version_tuple = _import_blender_adaptor_version_tuple()

        packages: list[str] = []
        try:
            import bpy  # ty:ignore[unresolved-import]

            # https://docs.blender.org/api/current/bpy.app.html#bpy.app.version
            blender_version = ".".join(str(v) for v in bpy.app.version[:2])
        except Exception:  # ruff:ignore[blind-except]
            blender_version = None

        # note: this is used to get the version of the adaptor, which is
        # not necessarily the same as the Blender version. Sometimes it happens
        # that the version in dev build is set incorrectly? to 0.0 and then
        # the submitted jobs will fail because that conda package can't be
        # found in the default conda channel. This simple fix will release
        # the version constrain in that case.
        adaptor_version = ".".join(str(v) for v in adaptor_version_tuple[:2])
        adaptor_version = f"={adaptor_version}.*"
        if adaptor_version_tuple[0] == 0 and adaptor_version_tuple[1] == 0:
            adaptor_version = ""
        packages.extend(
            (
                f"blender={blender_version}.*",
                f"blender-openjd{adaptor_version}",
            ))

        return packages

    def _get_conda_pkgs_for_nuke(self) -> list[str]:  # ruff:ignore[no-self-use]
        """Get a list of conda packages for Nuke.

        Returns:
            A list of conda packages for Nuke

        """
        from deadline.nuke_submitter._version import (  # ruff:ignore[import-private-name]
            version_tuple as adaptor_version_tuple,
        )

        packages: list[str] = []
        try:
            import nuke  # ty:ignore[unresolved-import]

            nuke_version = nuke.NUKE_VERSION_MAJOR
        except Exception:  # ruff:ignore[blind-except]
            nuke_version = None

        # note: this is used to get the version of the adaptor, which is
        # not necessarily the same as the Nuke version. Sometimes it happens
        # that the version in dev build is set incorrectly? to 0.0 and then
        # the submitted jobs will fail because that conda package can't be
        # found in the default conda channel. This simple fix will release
        # the version constrain in that case.
        adaptor_version = ".".join(str(v) for v in adaptor_version_tuple[:2])
        adaptor_version = f"={adaptor_version}.*"
        if adaptor_version_tuple[0] == 0 and adaptor_version_tuple[1] == 0:
            adaptor_version = ""
        packages.extend(
            (
                f"nuke={nuke_version}.*",
                f"nuke-openjd{adaptor_version}",
            ))

        return packages


def auto_detect_conda_packages(
        host_name: str, job_template: dict[str, Any]) -> str:
    """Auto-detects conda packages for a given host and job template.

    In the normal GUI flow, the submitter detects the Maya version and active
    renderers and builds a CondaPackages string like:
        "maya=2024.* maya-openjd=0.7.* maya-vray"
    In headless/AYON mode the GUI is never shown, so we do the same detection
    here. Renderer names are extracted from the job template's step initData
    (each step embeds ``renderer: <name>`` in its YAML init data).

    Args:
        host_name: Name of the current host app.
        job_template: The job template dict (already generated).

    Returns:
        A space-separated CondaPackages string, or empty string on failure.

    Raises:
        NotImplementedError: When the host isn't implemented, and so
            we can't detect conda packages.
        ValueError: When there is error getting the conda packages.

    """
    # get host specific packages
    hcp = HostCondaPackages(job_template)
    host_function = f"_get_conda_pkgs_for_{host_name}"
    try:
        conda_packages: list[str] = getattr(hcp, host_function)()
    except AttributeError as e:
        msg = f"Cannot find conda packages for {host_name} - not implemented."
        raise NotImplementedError(msg) from e
    except Exception as e:
        msg = f"Cannot detect conda packages for {host_name}."
        raise ValueError(msg) from e
    return " ".join(conda_packages)
