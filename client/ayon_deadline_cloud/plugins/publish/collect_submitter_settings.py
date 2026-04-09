"""Collect AWS Deadline Cloud submitter settings."""
from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar

import pyblish.api
from deadline import client
from deadline.maya_submitter.data_classes import RenderSubmitterUISettings
from deadline.maya_submitter.maya_render_submitter import (
    get_queue_parameters,
)

if TYPE_CHECKING:
    from logging import Logger


class CollectSubmitterSettings(pyblish.api.ContextPlugin):
    """Collect settings from AWS Deadline Cloud Submitter UI."""
    label = "Collect AWS Deadline Cloud Submitter Settings"
    order = pyblish.api.CollectorOrder + 0.1
    targets: ClassVar[list[str]] = ["local"]
    log: Logger

    def process(self, context: pyblish.api.Context) -> None:
        """Collect settings from Deadline Maya Submitter UI.

        Args:
            context: Pyblish context to store collected data in.

        """
        render_settings = RenderSubmitterUISettings()
        profile_name = client.config.get_setting("defaults.aws_profile_name")
        default_farm_id = client.config.get_setting("defaults.farm_id")
        queue_id = client.config.get_setting("defaults.queue_id")
        queue_parameters: list[dict[str, Any]] = get_queue_parameters()

        context.data["deadline_cloud_submitter_settings"] = {
            "profile_name": profile_name,
            "default_farm_id": default_farm_id,
            "queue_id": queue_id,
            "queue_parameters": queue_parameters,
            "render_settings": dataclasses.asdict(render_settings),
        }
