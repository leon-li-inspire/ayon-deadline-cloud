"""Server-side add-on implementation."""
from typing import Type

from ayon_server.addons import BaseServerAddon

from .settings import DEFAULT_VALUES, DeadlineCloudSettings


class DeadlineCloudAddon(BaseServerAddon):
    """Add-on class for the server."""
    settings_model: Type[DeadlineCloudSettings] = DeadlineCloudSettings

    async def get_default_settings(self) -> DeadlineCloudSettings:
        """Return default settings."""
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_VALUES)
