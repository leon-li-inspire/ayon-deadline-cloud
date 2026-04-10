"""Create Deadline Cloud Job."""
from __future__ import annotations
from ayon_maya import plugin


class CreateDeadlineCloudJob(plugin.Creator):
    """Creator plugin for AWS Deadline Cloud Render Job."""
    identifier = "io.ayon.create.deadline_cloud_job"
    label = "Deadline Cloud Render Job"
    family = "deadline_cloud_job"
