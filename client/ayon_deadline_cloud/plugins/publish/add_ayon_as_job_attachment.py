"""Add AYON dependencies as a job attachment.

This plugin will add AYON Launcher, addons and dependency package
and add it as a job attachments. This is cached so if this is
already present on S3 it won't get re-uploaded.

Having AYON as job attachments allows running publishing on
both SMF and CMF where there is no AYON available.

"""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from pprint import pformat
from typing import TYPE_CHECKING, Any, ClassVar, Self
from urllib.parse import urlencode

import ayon_api
import pyblish.api
from ayon_core.lib import get_addons_resources_dir
from ayon_core.pipeline.publish import PublishError
from ayon_deadline_cloud.addon import (
    DeadlineCloudAddon,
)
from botocore.exceptions import (
    ClientError,
)

# from deadline import client
from xxhash import xxh3_128

if TYPE_CHECKING:
    from logging import Logger

    #     import boto3
    from ayon_api.typing import (
        AddonInfoDict,
        BundleInfoDict,
        DependencyPackageDict,
    )
    from boto3.s3 import S3Client
    from boto3.session import Session


CHUNK_SIZE = 8192

# path delimiters for local storage
DPKG_DELIMITER = "dpkg"
ADDONS_DELIMITER = "addons"

HashPathTuple = tuple[str, Path]


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


class NotClientAddonError(Exception):
    """Raised when addon doesn't have client part."""


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


@dataclass
class AddonVersionInfo:
    """Addon version information."""
    version: str
    full_name: str
    filename: str
    title: str | None = None
    checksum: str | None = None
    checksum_algorithm: str | None = None

    @classmethod
    def from_dict(
        cls,
        addon_name: str,
        addon_title: str,
        addon_version: str,
        version_data: dict[str, Any],
    ) -> Self:
        """Addon version info.

        Args:
            addon_name (str): Name of addon.
            addon_title (str): Title of addon.
            addon_version (str): Version of addon.
            version_data (dict[str, Any]): Addon version information from
                server.

        Returns:
            AddonVersionInfo: Addon version info.

        Raises:
            ValueError: if addon information cannot be found or
                the addon source if of different type than `server`.
            NotClientAddonError: if addon doesn't have client source
                    information.

        """
        full_name = f"{addon_name}_{addon_version}"
        title = f"{addon_title} {addon_version}"
        filename: str | None = None

        source_info: list[dict[str, str]] = version_data.get(
            "clientSourceInfo")
        if not source_info:
            msg = (
                f"Cannot determine source information for {full_name} addon"
            )
            raise NotClientAddonError(msg)
        for source in source_info:
            if source["type"] == "server":
                filename = source.get("filename")
                break

        if not filename:
            msg = (
                f"Cannot determine filename for {full_name} addon "
                "from server source information"
            )
            raise ValueError(msg)

        checksum = version_data.get("checksum")
        if checksum is None:
            checksum = version_data.get("hash")

        return cls(
            version=addon_version,
            full_name=full_name,
            filename=filename,
            checksum=checksum,
            checksum_algorithm=version_data.get("checksumAlgorithm", "sha256"),
            title=title,
        )


@dataclass
class AddonInfo:
    """Object matching JSON payload from Server."""
    name: str
    title: str
    versions: dict[str, AddonVersionInfo]
    description: str | None = None
    license: str | None = None
    authors: str | None = None

    @classmethod
    def from_dict(cls, data: AddonInfoDict) -> Self:
        """Addon info by available versions.

        Args:
            data (dict[str, Any]): Addon information from server. Should
                contain information about every version under 'versions'.

        Returns:
            AddonInfo: Addon info with available versions.

        """
        # server payload contains info about all versions
        addon_name = data["name"]
        title = data.get("title") or addon_name

        src_versions = data.get("versions") or {}
        dst_versions = {
            addon_version: AddonVersionInfo.from_dict(
                addon_name, title, addon_version, version_data
            )
            for addon_version, version_data in src_versions.items()
        }
        return cls(
            name=addon_name,
            title=title,
            versions=dst_versions,
            description=data.get("description"),
            license=data.get("license"),
            authors=data.get("authors")
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
    label = "Add AYON Components as a job attachment"
    # make sure it runs after the data is collected
    order = pyblish.api.IntegratorOrder
    targets: ClassVar[list[str]] = ["local"]
    families: ClassVar[list[str]] = ["deadline_cloud"]
    log: Logger

    def __init__(self):
        """Constructor."""
        super().__init__()
        self._s3_bucket: str | None = None
        self._s3_prefix: str | None = None
        self._s3_client: S3Client | None = None
        self._ayon_components_cache_folder: Path | None = None
        self.resource_dir: Path | None = None

    def process(self, instance: pyblish.api.Instance) -> None:
        """Process this instance.

        Args:
            instance: Instance to process.

        Raises:
            PublishError: Publish failed.


        """
        settings = (
            instance.context.data["deadline_cloud_submitter_settings"])
        # farm_id = settings["default_farm_id"]
        # queue_id = settings["queue_id"]
        # session: Session = client.api.get_boto3_session()

        if settings.get("worker_platform", "linux") == "hybrid":
            worker_platforms = {"windows", "linux"}
        else:
            worker_platforms = {settings.get("worker_platform", "linux")}

        # default point to addons resources folder
        self._ayon_components_cache_folder = Path(
            get_addons_resources_dir(
                addon_name=DeadlineCloudAddon.name
            )
        ) / "cache"

        # if set in settings, override
        if settings.get("ayon_components_cache_folder"):
            self._ayon_components_cache_folder = Path(
                settings["ayon_components_cache_folder"]["platform_name"])

        # finally, env var rules them all
        if os.getenv("AYON_COMPONENTS_CACHE_FOLDER"):
            self._ayon_components_cache_folder = Path(
                os.getenv("AYON_COMPONENTS_CACHE_FOLDER", "")
            )

        # expand variables
        self._ayon_components_cache_folder = (
            self._ayon_components_cache_folder.expanduser().resolve()
        )

        if not self._ayon_components_cache_folder:
            msg = "AYON Component Cache folder isn't resolved."
            raise PublishError(msg)

        self.resource_dir = (
            self._ayon_components_cache_folder / DeadlineCloudAddon.name
        )

        """
        try:
            self._set_s3_session(session, farm_id, queue_id)
        except (ClientError, ValueError) as e:
            msg = f"Failed to set up S3 session: {e}"
            raise PublishError(msg) from e

        if not self._s3_client or not self._s3_bucket or not self._s3_prefix:
            msg = "S3 session is not properly configured."
            raise PublishError(msg)
        """

        # get the dependency package(s)
        bundle_name = os.getenv("AYON_BUNDLE_NAME")
        if not bundle_name:
            msg = "Cannot determine current bundle name."
            raise PublishError(msg)

        try:
            dependency_packages = self.get_dependency_packages(
                bundle_name=bundle_name,
                platforms=worker_platforms,
                project_name=instance.context.data.get("projectName")
            )
        except (ValueError, RuntimeError) as e:
            msg = f"Failed to get dependency packages: {e}"
            raise PublishError(msg) from e

        # get addons and build manifest
        try:
            addons = self.get_addons(
                bundle_name=bundle_name,
                project_name=instance.context.data.get("projectName")
            )
        except ValueError as e:
            msg = f"Failed to get addons: {e}"
            raise PublishError(msg) from e

        # add lists to job attachments:
        self.log.debug(pformat(instance.data
            ["deadline_cloud_job_data"]
            ["assetReferences"]))
        all_attachments = dependency_packages + addons
        instance.data["jobAttachments"] = all_attachments
        addon_dir = self.resource_dir / ADDONS_DELIMITER
        dpkg_dir = self.resource_dir / DPKG_DELIMITER

        (
            instance.data
            ["deadline_cloud_job_data"]
            ["assetReferences"]
            ["assetReferences"]
            ["inputs"]
            ["directories"]
        ).append(addon_dir.as_posix())
        (
            instance.data["deadline_cloud_job_data"]["assetReferences"][
                "assetReferences"
            ]["inputs"]["directories"]
        ).append(dpkg_dir.as_posix())
        """
        existing_filenames = (
            instance.data
            ["deadline_cloud_job_data"]
            ["assetReferences"]
            ["assetReferences"]
            ["inputs"]
            ["filenames"]
        )
        existing_filenames += [path.as_posix() for _, path in all_attachments]
        self.log.debug(
            "Adding %s as job attachments",
            pformat([path.as_posix() for _, path in all_attachments]))
        """

    def get_dependency_packages(
            self,
            bundle_name: str,
            platforms: set[str],
            project_name: str
    ) -> list[HashPathTuple]:
        """Get dependency packages from the server.

        Args:
            bundle_name: Name of the bundle.
            platforms: Set of platforms to get the dependency packages for.
            project_name: Name of the project.

        Returns:
            list of tuples with xxh3_128 has and file paths.

        Raises:
            ValueError: If dependency package cannot be determined.
            RuntimeError: When dependency package cannot be downloaded
                from the server.
        """
        result = []
        dependency_packages: list[DependencyPackage] = []
        if not self.resource_dir:
            msg = "Addon resource directory cannot be determined."
            raise ValueError(msg)

        for worker_platform in platforms:
            dependency_package = self.get_bundle_dependency_package(
                bundle_name,
                worker_platform,
                project_name,
            )
            if not dependency_package:
                msg = (
                    "Cannot determine dependency package "
                    f"for the platform {worker_platform} and "
                    f"the bundle {bundle_name}."
                )
                raise ValueError(msg)
            dependency_packages.append(dependency_package)
        for pkg in dependency_packages:
            local_dpkg_path = (
                    self.resource_dir / DPKG_DELIMITER
                    / pkg.platform / pkg.filename
            )

            if not local_dpkg_path.exists():
                # We need to download it first from the AYON server
                # to calculate the hash for S3 to check if there is the
                # object and wheter it is the same
                downloaded_dpkg = ayon_api.download_dependency_package(
                    src_filename=pkg.filename,
                    dst_directory=str(self.resource_dir),
                    dst_filename=pkg.filename,
                    platform_name=pkg.platform,
                    chunk_size=CHUNK_SIZE,
                )
                if not downloaded_dpkg:
                    msg = (
                        "Failed to download dependency package "
                        f"{pkg.filename} ({pkg.platform} from AYON server."
                    )
                    raise RuntimeError(msg)
                local_dpkg_path = Path(downloaded_dpkg)

            # calculate the hash of the file
            hasher = xxh3_128()
            with open(local_dpkg_path, "rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    hasher.update(str(chunk))
            local_hash = hasher.hexdigest()
            result.append((local_hash, local_dpkg_path))
        return result

    def get_addons(
            self, bundle_name: str, project_name: str) -> list[HashPathTuple]:
        """Get addons from the server.

        Args:
            bundle_name: Name of the bundle.
            project_name: Name of the project.

        Returns:
            list of tuples with xxh3_128 has and file paths.

        Raises:
            ValueError:

        """
        result = []
        addons = self.get_bundle_addon_versions(
            bundle_name=bundle_name, project_name=project_name
        )

        server_info = ayon_api.get_addons_info(details=True)
        addons_info = server_info["addons"]
        all_addons = {}
        for addon in addons_info:
            try:
                addon_info = AddonInfo.from_dict(addon)
            except NotClientAddonError:
                continue
            all_addons[addon_info.name] = addon_info

        for addon_name, addon_version in addons.items():
            try:
                addon_info: AddonInfo = all_addons[addon_name]
            except KeyError:
                self.log.debug("Skipping %s", addon_name)
                continue
            addon_filename = addon_info.versions[addon_version].filename
            local_addon_path = Path(
                get_addons_resources_dir(addon_name=DeadlineCloudAddon.name)
            ) / ADDONS_DELIMITER / addon_info.name / addon_version / addon_filename  # noqa: E501
            if not local_addon_path.exists():
                local_addon_path.parent.mkdir(parents=True, exist_ok=True)
                local_addon_path = Path(ayon_api.download_addon_private_file(
                    addon_info.name,
                    addon_version,
                    addon_filename,
                    local_addon_path.parent.as_posix(),
                    addon_filename,
                    CHUNK_SIZE))

                if not local_addon_path.exists():
                    msg = (
                        f"Addon {addon_name} version {addon_version} "
                        "cannot be downloaded from the server."
                    )
                    raise ValueError(msg)

            # calculate the hash of the file
            hasher = xxh3_128()
            with open(local_addon_path, "rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    hasher.update(str(chunk))
            local_hash = hasher.hexdigest()
            result.append((local_hash, local_addon_path))

        return result

    def _set_s3_session(
            self,
            session: Session, farm_id: str, queue_id: str) -> None:
        """Set up S3 session.

        Args:
            session: S3 session.
            farm_id: Farm ID.
            queue_id: Queue ID.

        """
        (
            bucket,
            prefix,
        ) = self.get_s3_settings_from_queue(
            session, farm_id, queue_id
        )

        s3_client: S3Client = session.client("s3")

        s3_client.head_bucket(Bucket=bucket)
        self.log.info("✓ Bucket access confirmed")

        self._s3_bucket = bucket
        self._s3_prefix = prefix
        self._s3_client = s3_client

    @staticmethod
    def hash_exists_on_s3(
            file_hash: str, bucket: str, s3_client: S3Client) -> bool:
        """Check if file exists on S3.

        Args:
            file_hash: File hash to check.
            bucket: Bucket to check.
            s3_client: S3 client.

        Returns:
            True if file exists on S3.

        Raises:
            ClientError: When S3 client encounters an error
                other than 404 Not Found.
        """
        # check for the object in S3
        s3_key = f"DeadlineCloud/Data/{file_hash}.xxh128"
        try:
            s3_client.head_object(
                Bucket=bucket,
                Key=s3_key,
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "404":
                return False
            raise
        else:
            return True

    @staticmethod
    def get_s3_settings_from_queue(
        session: Session,
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
        matching the behavior of ``AYONDistribution`` internally.

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
