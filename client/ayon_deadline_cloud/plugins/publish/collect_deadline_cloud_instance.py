"""Collect instances to be submitted to AWS Deadline Cloud."""
from __future__ import annotations

from typing import ClassVar

import pyblish.api


class CollectDeadlineCloudInstances(pyblish.api.ContextPlugin):
    """Collect instances to be submitted to AWS Deadline Cloud."""
    label = "Collect AWS Deadline Cloud Instances"
    order = pyblish.api.CollectorOrder + 0.1
    targets: ClassVar[list[str]] = ["local"]

    def process(self, context: pyblish.api.Context) -> None:
        """Collect instances to be submitted to AWS Deadline Cloud.

        Find all instances with `instance.data["farm"]`
        and add "deadline_cloud" family to them. This will mark them for
        submission to AWS Deadline Cloud in the submitter plugin.

        Args:
            context: Pyblish context to store collected data in.

        """
        for instance in context:
            if instance.data.get("productBaseType") != "deadline_cloud":
                continue

            instance.data["families"].append("deadline_cloud")
            instance.data["integrate"] = False
            # add empty representation to bypass Maya Instance Empty
            # validation. Ugly, but it works since the instance
            # isn't integrated.
            instance.data["representations"] = {}
