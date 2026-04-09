"""Deadline Cloud Addon for AYON."""
from __future__ import annotations

import os
from typing import Optional

from ayon_core.addon import AYONAddon, IPluginPaths

from .version import __version__

DEADLINE_CLOUD_ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))


class DeadlineCloudAddon(AYONAddon, IPluginPaths):
    """Deadline Cloud Addon for AYON."""
    name = "deadline_cloud"
    version = __version__

    @staticmethod
    def get_publish_plugin_paths(
         host_name: Optional[str] = None
    ) -> list[str]:
        """Return list of paths to publish plugins.

        Args:
            host_name: Optional name of the host application
                to get specific plugin paths.

        Returns:
            List of paths to publish plugins.

        """
        return [os.path.join(
            DEADLINE_CLOUD_ADDON_ROOT, "plugins", "publish")]
