"""Deadline Cloud Addon for AYON."""
from __future__ import annotations

import os
from typing import Any, Optional

from ayon_core.addon import AYONAddon, IPluginPaths

from .version import __version__

DEADLINE_CLOUD_ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))


class DeadlineCloudAddon(AYONAddon, IPluginPaths):
    """Deadline Cloud Addon for AYON."""
    name = "deadline_cloud"
    version = __version__

    @staticmethod
    def add_implementation_envs(
        env: dict[str, str], _app: Any) -> None:  # noqa: ANN401
        """Add environment variables for the addon implementation.

        Args:
            env: Dictionary of environment variables to be updated with
                implementation specific variables.
            _app: Name of the host application to add specific environment
                variables for.

        """
        # TODO(antirotor): Implement this env variable to set AYON scoped
        # Deadline Cloud configuration file path for the client to use.
        # env["DEADLINE_CONFIG_FILE_PATH"] = ...

    @staticmethod
    def get_publish_plugin_paths(
         host_name: Optional[str] = None  # noqa: ARG004
    ) -> list[str]:  # ty:ignore[invalid-method-override]
        """Return list of paths to publish plugins.

        Args:
            host_name: Optional name of the host application
                to get specific plugin paths.

        Returns:
            List of paths to publish plugins.

        """
        return [os.path.join(
            DEADLINE_CLOUD_ADDON_ROOT, "plugins", "publish")]

    @staticmethod
    def get_create_plugin_paths(
         host_name: Optional[str] = None
    ) -> list[str]:  # ty:ignore[invalid-method-override]
        """Return list of paths to creator plugins.

        Args:
            host_name: Optional name of the host application
                to get specific plugin paths.

        Returns:
            List of paths to creator plugins.

        """
        return [os.path.join(
            DEADLINE_CLOUD_ADDON_ROOT,
            "plugins", "create", host_name or "global")]

    @staticmethod
    def get_launch_hook_paths(app: str) -> list[str]:  # noqa: ARG004
        """Return list of paths to launch hooks.

        Args:
            app: Name of the host application
                to get specific hook paths.

        Returns:
            List of paths to launch hooks.

        """
        return [os.path.join(
            DEADLINE_CLOUD_ADDON_ROOT, "hooks")]
