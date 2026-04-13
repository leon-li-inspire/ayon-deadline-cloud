"""Create job bundle and submit to AWS Deadline Cloud."""
from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING, ClassVar

import pyblish.api
from deadline.client.api import create_job_from_job_bundle
from deadline.client.job_bundle._yaml import (  # noqa: PLC2701
    deadline_yaml_dump,
)

if TYPE_CHECKING:
    from logging import Logger


class SubmitToDeadlineCloud(pyblish.api.InstancePlugin):
    """Submit job to AWS Deadline Cloud."""
    """Create job bundle and submit to AWS Deadline Cloud."""
    label = "Submit to AWS Deadline Cloud"
    order = pyblish.api.IntegratorOrder + 0.1
    targets: ClassVar[list[str]] = ["local"]
    families: ClassVar[list[str]] = ["deadline_cloud"]
    log: Logger

    def process(self, instance: pyblish.api.Instance) -> None:
        """Create job bundle and submit to AWS Deadline Cloud.

        Craete temporary directory, dump collected job data
        (job template, parameter values and asset references)
        to it as YAML files and submit the job bundle to AWS Deadline Cloud.

        Args:
            instance: Pyblish instance with collected job data in context.

        """
        if not instance.context.data.get("deadline_cloud_job_data"):
            self.log.warning(
                "No job data collected for AWS Deadline Cloud. "
                "Skipping submission.")
            return
        job_data = instance.context.data["deadline_cloud_job_data"]
        self.log.info(
            "Creating job bundle and submitting to AWS Deadline Cloud...")
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/template.yaml", "w", encoding="utf8") as f:
                deadline_yaml_dump(
                    job_data["job_template"],
                    f,
                    indent=1
                )
            with open(
                    f"{temp_dir}/parameter_values.yaml",
                    "w",
                    encoding="utf8") as f:
                deadline_yaml_dump(
                    {"parameterValues": job_data["parameter_values"]},
                    f,
                    indent=1
                )
            with open(
                    f"{temp_dir}/asset_references.yaml",
                    "w",
                    encoding="utf8") as f:
                deadline_yaml_dump(
                    job_data["asset_references"],
                    f,
                    indent=1
                )
            self.log.info("Submitting job bundle to AWS Deadline Cloud...")
            job_id = create_job_from_job_bundle(temp_dir)
            self.log.info(
                "Job submitted to AWS Deadline Cloud with ID: %s",
                job_id)
