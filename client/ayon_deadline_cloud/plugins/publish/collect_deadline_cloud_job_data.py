"""Collect AWS Deadline Cloud Job Data."""
from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar

import pyblish.api
from deadline import client
from deadline.client.job_bundle.submission import AssetReferences
from deadline.maya_submitter.data_classes import RenderSubmitterUISettings
from deadline.maya_submitter.maya_render_submitter import (
    get_asset_references_for_submission,
    get_job_template_for_submission,
    get_parameter_values_for_submission,
    get_queue_parameters,
)

if TYPE_CHECKING:
    from logging import Logger


class CollectDeadlineCloudJobData(pyblish.api.ContextPlugin):
    """Collect job data from AWS Deadline Cloud Submitter UI."""
    label = "Collect AWS Deadline Cloud Job Data"
    order = pyblish.api.CollectorOrder + 0.1
    targets: ClassVar[list[str]] = ["local"]
    families: ClassVar[list[str]] = ["deadline_cloud"]
    log: Logger

    def process(self, context: pyblish.api.Context) -> None:
        """Collect job data from Deadline Maya Submitter UI.

        Args:
                context: Pyblish context to store collected data in.

        """
        settings = RenderSubmitterUISettings()
        queue_parameters: list[dict[str, Any]] = get_queue_parameters()
        asset_references = AssetReferences(
            input_filenames=set(settings.input_filenames),
            input_directories=set(settings.input_directories),
            output_directories=set(settings.output_directories),
        )

        # this would be 'job_bundle/template.yaml'
        job_template = get_job_template_for_submission(settings)
        # this would be 'job_bundle/parameter_values.yaml'
        parameter_values = get_parameter_values_for_submission(
            settings, queue_parameters)
        # this would be 'job_bundle/asset_references.yaml'
        asset_refs_dict = get_asset_references_for_submission(asset_references)

        self.log.info(
            "Collected job data for AWS Deadline Cloud: ")
        context.data["deadline_cloud_job_data"] = {
            "job_template": job_template,
            "parameter_values": parameter_values,
            "asset_references": asset_refs_dict,
        }
        self.log.info(
            "Collected job data for AWS Deadline Cloud.")

        profile_name = client.config.get_setting("defaults.aws_profile_name")
        default_farm_id = client.config.get_setting("defaults.farm_id")
        queue_id = client.config.get_setting("defaults.queue_id")
        queue_parameters: list[dict[str, Any]] = get_queue_parameters()

        context.data["deadline_cloud_submitter_settings"] = {
            "profile_name": profile_name,
            "default_farm_id": default_farm_id,
            "queue_id": queue_id,
            "queue_parameters": queue_parameters,
            "render_settings": dataclasses.asdict(settings),
        }
        self.log.info(
            "Collected submitter settings for AWS Deadline Cloud.")
