"""Create job bundle and submit to AWS Deadline Cloud."""
from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING, ClassVar

import pyblish.api
from deadline.client.api import create_job_from_job_bundle
from deadline.client.job_bundle._yaml import (  # noqa: PLC2701
    deadline_yaml_dump,
)
from deadline.client.job_bundle.submission import AssetReferences

if TYPE_CHECKING:
    from logging import Logger


class SubmitToDeadlineCloud(pyblish.api.InstancePlugin):
    """Submit job to AWS Deadline Cloud."""
    label = "Submit Job to AWS Deadline Cloud"
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
        if not instance.data.get("deadline_cloud_job_data"):
            self.log.warning(
                "No job data collected for AWS Deadline Cloud. "
                "Skipping submission.")
            return
        job_data = instance.data["deadline_cloud_job_data"]

        known_paths = self._collect_known_asset_paths(job_data)

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
            job_id = create_job_from_job_bundle(
                job_bundle_dir=temp_dir,
                # known_asset_paths=known_paths,
                # interactive_confirmation_callback=lambda _msg, _default: True,
                print_function_callback=self.log.info,
            )
            self.log.info(
                "Job submitted to AWS Deadline Cloud with ID: %s",
                job_id)

    @staticmethod
    def _collect_known_asset_paths(
            job_data: dict,
    ) -> list[str]:
        """Derive known asset paths from job data.

        Returns:
            list[str]: Deduplicated, normalized paths treated as known assets.
        """
        template = job_data.get("job_template", {})
        path_param_names = SubmitToDeadlineCloud._collect_path_parameter_names(
            template
        )

        paths = SubmitToDeadlineCloud._collect_asset_reference_paths(job_data)
        paths.update(
            SubmitToDeadlineCloud._collect_parameter_value_paths(
                job_data.get("parameter_values", []),
                path_param_names,
            )
        )
        return list(paths)

    @staticmethod
    def _collect_asset_reference_paths(job_data: dict) -> set[str]:
        """Collect known paths from asset references in job data.

        Args:
            job_data: Pyblish job data.

        Returns:
            set[str]: Deduplicated, normalized paths.

        """
        paths: set[str] = set()
        refs = AssetReferences.from_dict(job_data.get("asset_references"))

        for filename in refs.input_filenames:
            parent = os.path.dirname(os.path.abspath(filename))
            if parent:
                paths.add(parent)
        paths.update(os.path.abspath(directory)
                     for directory
                     in refs.input_directories)
        paths.update(os.path.abspath(directory)
                     for directory
                     in refs.output_directories)
        return paths

    @staticmethod
    def _collect_path_parameter_names(template: dict) -> set[str]:
        """Collect parameter names that are declared as PATH type.

        Args:
            template: Pyblish job template.

        Returns:
            set[str]: Set of parameter names that are of PATH type.

        """
        path_param_names: set[str] = set()
        for param_def in template.get("parameterDefinitions", []):
            if param_def.get("type") == "PATH":
                path_param_names.add(param_def["name"])
        return path_param_names

    @staticmethod
    def _collect_parameter_value_paths(
            parameter_values: list[dict],
            path_param_names: set[str],
    ) -> set[str]:
        """Collect normalized paths from PATH-type parameter values.

        Args:
            parameter_values: Pyblish job parameters.
            path_param_names: Set of parameter names that
                are of PATH-type parameters.

        Returns:
            set[str]: Deduplicated, normalized paths.

        """
        paths: set[str] = set()
        for parameter_value in parameter_values:
            name = parameter_value.get("name", "")
            value = parameter_value.get("value", "")
            if not value or name not in path_param_names:
                continue

            abspath = os.path.abspath(value)
            # For files add parent dir, for dirs add directly.
            if os.path.splitext(abspath)[1]:
                paths.add(os.path.dirname(abspath))
            else:
                paths.add(abspath)
        return paths
