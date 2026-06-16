"""Add AYON dependencies as a job attachment.

This plugin will add AYON Launcher, addons and dependency package
and add it as a job attachments. This is cached so if this is
already present on S3 it won't get re-uploaded.

Having AYON as job attachemnts allows running publishing on
both SMF and CMF where there is no AYON available.

"""
from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urlencode

import ayon_api
import boto3
import pyblish.api
from ayon_core.pipeline.publish import PublishError
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
)
from deadline import client
from xxhash import xxh3_128

if TYPE_CHECKING:
    from logging import Logger

    from ayon_api.typing import (
        BundleInfoDict,
        BundlesInfoDict,
        DependencyPackageDict,
    )


CHUNK_SIZE = 8192


class BundleNotFoundError(Exception):
    """Raised when the requested bundle is not available on the server.

    Args:
        bundle_name (str): Name of the bundle that was not found.

    """

    def __init__(self, bundle_name: str):
        """Constructor."""
        self.bundle_name = bundle_name
        super().__init__(
            f"Bundle '{bundle_name}' is not available on server"
        )


@dataclass
class DependencyPackage:
    """Minimal representation of a server-side dependency package.

    Attributes:
        filename (str): Package filename (also used as its identifier).
        platform (str): Target platform (``"windows"``, ``"linux"``,
            ``"darwin"``).
        checksum (str): File checksum.
        checksum_algorithm (str): Algorithm used for ``checksum``
            (e.g. ``"sha256"``).
        python_modules (dict[str, str]): Python package name → version
            pinned inside the package.
        source_addons (dict[str, str]): Addon name → version that were
            used to build this package.
        sources (list[dict[str, Any]]): Raw source entries exactly as
            returned by the server (type/url/path/etc.).

    """

    filename: str
    platform: str
    checksum: str
    checksum_algorithm: str
    python_modules: dict[str, str] = field(default_factory=dict)
    source_addons: dict[str, str] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_server_data(
            cls, data: DependencyPackageDict) -> DependencyPackage:
        """Construct from a single package entry in the server response.

        Args:
            data (DependencyPackageDict): One element from
                ``ayon_api.get_dependency_packages()["packages"]``.

        Returns:
            DependencyPackage: Populated instance.

        """
        return cls(
            filename=data["filename"],
            platform=data["platform"],
            checksum=data["checksum"],
            checksum_algorithm=data.get("checksumAlgorithm", "sha256"),
            python_modules=data.get("pythonModules") or {},
            source_addons=data.get("sourceAddons") or {},
            sources=data.get("sources") or [],
        )


def _get_bundle_data(
    bundle_name: str,
    bundles_info: list[BundleInfoDict],
) -> BundleInfoDict:
    bundle_data = next(
        (b for b in bundles_info if b["name"] == bundle_name),
        None,
    )
    if bundle_data is None:
        raise BundleNotFoundError(bundle_name)
    return bundle_data


def _get_project_bundle_name(
    bundle_data: BundleInfoDict,
    project_name: str,
) -> str | None:
    """Return the project-specific bundle override name, if any.

    Dev bundles skip project overrides (same behavior as
    ``AYONDistribution``).

    """
    if bundle_data.get("isDev"):
        return None

    project = ayon_api.get_project(project_name)
    project_bundles = (project or {}).get("data", {}).get("bundle", {})

    if bundle_data.get("isStaging"):
        override_name = project_bundles.get("staging")
    else:
        override_name = project_bundles.get("production")

    return override_name or None


class AddAYONAsJobAttachment(pyblish.api.InstancePlugin):
    """Add AYON dependencies as a job attachment."""
    label = "Add Publishing Step to the Job Template"
    # make sure it runs after the data is collected
    order = pyblish.api.IntegratorOrder
    targets: ClassVar[list[str]] = ["local"]
    families: ClassVar[list[str]] = ["deadline_cloud"]
    log: Logger

    def process(self, instance: pyblish.api.Instance) -> None:
        """Process this instance.

        Args:
            instance: Instance to process.

        Raises:
            PublishError: Publish failed.

        """
        settings = instance.context["deadline_cloud_submitter_settings"]
        session = client.api.get_boto3_session()

        # first, find out what is already uploaded
        (
            bucket,
            prefix,
        ) = self.get_s3_settings_from_queue(
            session,
            settings["default_farm_id"],
            settings["queue_id"]
        )

        s3_client = session.client("s3")

        try:
            s3_client.head_bucket(Bucket=bucket)
            self.log.info("✓ Bucket access confirmed")
        except ClientError as e:
            msg = "Cannot access S3 bucket."
            raise PublishError(msg) from e

        # get the dependency package
        bundle_name = os.getenv("AYON_BUNDLE_NAME")
        if not bundle_name:
            msg = "Cannot determine current bundle name."
            raise PublishError(msg)

        platform_name = platform.system().lower()
        dependency_package = self.get_bundle_dependency_package(
            bundle_name,
            platform_name,
            instance.context.data.get("projectName"),
        )
        dependency_package.checksum

        dependency_package_path = ayon_api.download_dependency_package(


        )

        d

    @staticmethod
    def get_s3_settings_from_queue(
        session: boto3.Session,
        farm_id: str,
        queue_id: str,
    ) -> tuple[str, str]:
        """Get S3 settings from Deadline Cloud queue configuration.

        Args:
            session: Boto3 session
            farm_id: Farm ID
            queue_id: Queue ID

        Returns:
            Tuple of (bucket, prefix)

        Raises:
            ValueError: If queue doesn't have job attachments configured

        """
        deadline_client = session.client("deadline")

        try:
            response = deadline_client.get_queue(
                farmId=farm_id,
                queueId=queue_id,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            msg = (
                "Failed to get queue configuration "
                f"({error_code}): {error_msg}")
            raise ValueError(msg) from e

        # Extract job attachment settings
        job_attachment_settings = response.get("jobAttachmentSettings")
        if not job_attachment_settings:
            msg = (
                f"Queue {queue_id} does not have job attachments configured. "
                "Please configure job attachments for this queue or use "
                "direct S3 specification.")
            raise ValueError(msg)

        bucket = job_attachment_settings.get("s3BucketName")
        prefix = job_attachment_settings.get("rootPrefix")

        if not bucket:
            msg = "Queue job attachment settings missing s3BucketName"
            raise ValueError(msg)
        if not prefix:
            msg = "Queue job attachment settings missing rootPrefix"
            raise ValueError(msg)

        return bucket, prefix

    @staticmethod
    def get_bundle_addon_versions(
            bundle_name: str,
            project_name: str | None = None,
    ) -> dict[str, str]:
        """Return addon name → version mapping for a known bundle.

        When *project_name* is provided the project's configured bundle
        override (production or staging) is resolved and its addon versions
        are merged with the studio bundle via the server settings API —
        matching the behaviour of ``AYONDistribution`` internally.

        Args:
            bundle_name (str): Name of the studio bundle.
            project_name (Optional[str]): Project name.  When given,
                project-level addon overrides are applied if configured.

        Returns:
            dict[str, str]: Mapping of addon name to version string.

        """
        bundles_info: list[BundleInfoDict] = ayon_api.get_bundles()["bundles"]
        bundle_data: BundleInfoDict = _get_bundle_data(
            bundle_name, bundles_info)

        if project_name:
            project_bundle_name = _get_project_bundle_name(
                bundle_data, project_name
            )
            if project_bundle_name and project_bundle_name != bundle_name:
                key_values = {
                    "summary": "true",
                    "bundle_name": bundle_name,
                    "project_bundle_name": project_bundle_name,
                }
                response = ayon_api.get(
                    f"settings?{urlencode(key_values)}")
                return {
                    addon["name"]: addon["version"]
                    for addon in response.data["addons"]
                }

        return dict(bundle_data.get("addons") or {})

    @staticmethod
    def get_bundle_dependency_package(
            bundle_name: str,
            platform_name: str | None = None,
            project_name: str | None = None,
    ) -> DependencyPackage | None:
        """Return the dependency package for a known bundle and platform.

        When *project_name* is provided the project's configured bundle
        override is detected; if that override specifies a different
        dependency package for the platform, that package is returned.

        Args:
            bundle_name (str): Name of the studio bundle.
            platform_name (Optional[str]): Platform name (``"windows"``,
                ``"linux"``, ``"darwin"``).  Defaults to the current
                platform when omitted.
            project_name (Optional[str]): Project name.  When given,
                project-level dependency package overrides are applied.

        Returns:
            Optional[DependencyPackage]: Matching package, or ``None`` when
                the bundle has no dependency package defined for the
                platform.

        """
        if platform_name is None:
            platform_name = platform.system().lower()

        bundles_info = ayon_api.get_bundles()["bundles"]
        bundle_data = _get_bundle_data(bundle_name, bundles_info)

        active_bundle_data = bundle_data
        if project_name:
            project_bundle_name = _get_project_bundle_name(
                bundle_data, project_name
            )
            if project_bundle_name and project_bundle_name != bundle_name:
                project_bundle_data = next(
                    (
                        b for b in bundles_info
                        if b["name"] == project_bundle_name
                    ),
                    None,
                )
                # Use the project bundle when it defines its own package for
                # the requested platform.
                if (
                        project_bundle_data
                        and project_bundle_data
                        .get("dependencyPackages", {})
                        .get(platform_name)
                ):
                    active_bundle_data = project_bundle_data

        pkg_filename = (
                active_bundle_data.get("dependencyPackages") or {}
        ).get(platform_name)
        if not pkg_filename:
            return None

        packages_info = ayon_api.get_dependency_packages()["packages"]
        pkg_data = next(
            (p for p in packages_info if p["filename"] == pkg_filename),
            None,
        )
        return DependencyPackage.from_server_data(
            pkg_data) if pkg_data else None
