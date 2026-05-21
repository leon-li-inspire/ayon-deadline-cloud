"""Create publishing instance from provided files."""
from __future__ import annotations

import mimetypes
import os
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, NamedTuple

import ayon_api
import clique
import pyblish.api
from ayon_core.pipeline import KnownPublishError
from ayon_core.pipeline.create import get_product_name
from ayon_core.pipeline.publish import (
    add_trait_representations,
)
from ayon_core.pipeline.traits import (
    FileLocation,
    FileLocations,
    FrameRanged,
    Image,
    MimeType,
)
from ayon_core.pipeline.traits import (
    Representation as TraitRepresentation,
)
from ayon_deadline_cloud.api.datatypes import (
    InstanceData,
    StandardRepresentation,
)

if TYPE_CHECKING:
    from logging import Logger


class RepresentationTuple(NamedTuple):
    """Representation named tuple."""
    standard: StandardRepresentation
    trait: TraitRepresentation


# Minimum number of characters a common prefix must have (after stripping
# trailing separators) to be considered "meaningful" for grouping.
_MIN_PREFIX_LEN = 2


def _common_stem_prefix(stems: list[str]) -> str:
    """Return the longest common leading substring shared by all *stems*.

    Unlike ``os.path.commonprefix`` this helper is not affected by any Ruff
    path-related lint rules, and the character-by-character comparison is
    intentional here because we are comparing file *stems*, not path
    components.

    Args:
        stems: list of filename stems (without extension).

    Returns:
        str: Longest common prefix, or empty string if there is none.

    """
    if not stems:
        return ""
    prefix = stems[0]
    for stem in stems[1:]:
        while not stem.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


class CreateInstancesFromFiles(pyblish.api.ContextPlugin):
    """Create publishing instances from provided files."""

    label = "Create publishing instances from files"
    # must run as soon as possible
    order = pyblish.api.CollectorOrder - 0.499
    hosts: ClassVar[list[str]] = ["shell"]
    targets: ClassVar[list[str]] = ["farm"]
    log: Logger

    def __init__(self):
        """Constructor."""
        self._context: pyblish.api.Context
        self._task_entity = None
        self._folder_entity = None

    def process(self, context: pyblish.api.Context) -> None:
        """Create publishing instances from provided files.

        Args:
            context: pyblish context.

        Raises:
            KnownPublishError: When folder or task cannot be found in AYON.

        """
        self._context: pyblish.api.Context = context
        self.log.info("Processing %s", context.data.get("outputPath"))
        if not context.data.get("outputPath"):
            msg = "Unable to find output path in context."
            raise KnownPublishError(msg)

        username = (
                context.data.get("user") or os.environ.get("AYON_USERNAME")
        )
        if username:
            # ayon-python-api does not have public api function to find
            # out if is used service user. So we need to have try-except.
            con = ayon_api.get_server_api_connection()
            with suppress(ValueError):
                con.set_default_service_username(username)

        folder_path: str = context.data["folderPath"]
        project_name: str = context.data["projectName"]
        self._folder_entity = ayon_api.get_folder_by_path(
            project_name=project_name,
            folder_path=folder_path,
        )
        if not self._folder_entity:
            msg = (
                f"Unable to find folder '{folder_path}' in project"
                f" '{project_name}'."
            )
            raise KnownPublishError(msg)

        self._task_entity = None
        if context.data.get("task"):
            self._task_entity = ayon_api.get_task_by_name(
                project_name=project_name,
                folder_id=self._folder_entity["id"],
                task_name=context.data["task"],
            )
            if not self._task_entity:
                msg = (
                    f"Unable to find task '{context.data['ask']}' "
                    f"in folder '{folder_path}' "
                    f"in project '{project_name}'."
                )
                raise KnownPublishError(msg)

        instances = self.get_instances(
            Path(context.data["outputPath"]))

        if not instances:
            self.log.warning("No instances detected.")
            return

        for instance in instances:
            pyblish_instance = context.create_instance(
                name=instance.name)
            self.log.info("Creating instance %s", instance.name)
            pyblish_instance.data.update(asdict(instance))
            add_trait_representations(
                pyblish_instance,
                pyblish_instance.data.pop(
                    "trait_representations")
            )

            pyblish_instance.data["representations"] = (
                    pyblish_instance.data.pop("standard_representations")
            )

            # handle cleanupFullPaths
            context.data["cleanupFullPaths"] = []
            context.data["cleanupEmptyDirs"] = []

        from pprint import pformat
        self.log.debug(pformat(context.data))

    @staticmethod
    def _make_trait_representation(
            reminder_path: Path) -> TraitRepresentation:
        """Build a trait-based Representation for a single reminder file.

        Guesses MimeType from the file extension and adds Image trait
        when the mime type indicates an image.

        Args:
            reminder_path: Path to the reminder file

        Returns:
            TraitRepresentation: trait-based representation for the file.

        """
        mime_type_str, _ = mimetypes.guess_type(reminder_path)
        traits: list = [FileLocation(file_path=reminder_path)]
        if mime_type_str:
            traits.append(MimeType(mime_type=mime_type_str))
            if mime_type_str.startswith("image/"):
                traits.append(Image())
        return TraitRepresentation(name=reminder_path.stem, traits=traits)

    @staticmethod
    def _make_standard_representation(
            reminder_path: Path) -> StandardRepresentation:
        """Build a standard Representation for a single reminder file.

        Args:
            reminder_path (Path): Path to the reminder file.

        Returns:
            StandardRepresentation: standard representation for the file.

        """
        return StandardRepresentation(
            name=reminder_path.stem,
            ext=reminder_path.suffix,
            files=reminder_path.name,
            stagingDir=reminder_path.parent.as_posix(),
        )

    def _make_representations(
            self,
            reminder_path: Path
    ) -> RepresentationTuple:
        """Build both trait-based and standard Representations.

        Args:
            reminder_path: Path to the reminder file.

        Returns:
            RepresentationTuple: tuple
                with both representation types.

        """
        return RepresentationTuple(
            self._make_standard_representation(reminder_path),
            self._make_trait_representation(reminder_path)
        )

    @staticmethod
    def _make_collection_trait_representation(
            col: clique.Collection,
            staging_dir: Path,
            name: str,
    ) -> TraitRepresentation:
        """Build a trait-based Representation for a file sequence collection.

        Derives frame range from the collection indexes and guesses MimeType
        from the file extension.  An ``Image`` trait is appended when the
        mime type indicates an image.

        Args:
            col: clique.Collection describing the sequence.
            staging_dir: Directory that contains the sequence files.
            name: Name to assign to the representation.

        Returns:
            TraitRepresentation: trait-based representation for the sequence.

        """
        file_locations = [
            FileLocation(file_path=staging_dir / Path(f).name)
            for f in col
        ]
        ext = col.tail.lstrip(".")
        mime_type_str, _ = mimetypes.guess_type(f"file.{ext}")

        frame_start = min(col.indexes)
        frame_end = max(col.indexes)

        traits: list = [
            FileLocations(file_paths=file_locations),
            FrameRanged(frame_start=frame_start, frame_end=frame_end),
        ]
        if mime_type_str:
            traits.append(MimeType(mime_type=mime_type_str))
            if mime_type_str.startswith("image/"):
                traits.append(Image())
        return TraitRepresentation(name=name, traits=traits)

    @staticmethod
    def _make_collection_standard_representation(
            col: clique.Collection,
            staging_dir: Path,
            name: str,
    ) -> StandardRepresentation:
        """Build a standard Representation for a file sequence collection.

        Args:
            col: clique.Collection describing the sequence.
            staging_dir: Directory that contains the sequence files.
            name: Name to assign to the representation.

        Returns:
            StandardRepresentation: standard representation for the sequence.

        """
        files = [Path(f).name for f in col]
        return StandardRepresentation(
            name=name,
            ext=col.tail.lstrip("."),
            files=files,
            stagingDir=staging_dir.as_posix(),
        )

    def _make_collection_representations(
            self,
            col: clique.Collection,
            staging_dir: Path,
            name: str,
    ) -> RepresentationTuple:
        """Build trait-based and standard Representations for a collection.

        Args:
            col: clique.Collection describing the sequence.
            staging_dir: Directory that contains the sequence files.
            name: Name to assign to the representation.

        Returns:
            RepresentationTuple: tuple with both representation types.

        """
        return RepresentationTuple(
            self._make_collection_standard_representation(
                col, staging_dir, name),
            self._make_collection_trait_representation(
                col, staging_dir, name),
        )

    def _handle_collections(
            self,
            cols: list,
    ) -> list[InstanceData]:
        """Handle file sequence collections.

        Collections that share the same sequence pattern (head, padding, and
        frame indexes) but differ only in their file extension (e.g. ``.exr``
        vs ``.png``) are grouped into a single instance with one
        representation per extension.

        Args:
            cols: list of ``clique.Collection`` objects returned by
                ``clique.assemble``.

        Returns:
            list[InstanceData]: Created instances, one per unique sequence.

        """
        if not cols:
            return []

        # Group collections whose only difference is the file extension.
        # Key = (head, padding, frozenset of indexes) — collections in the
        # same group share the same sequence pattern and therefore belong to
        # the same product version.
        groups: dict[tuple, list] = {}
        for col in cols:
            key = (col.head, col.padding, frozenset(col.indexes))
            groups.setdefault(key, []).append(col)

        instances: list[InstanceData] = []
        for (head, _padding, _indexes), group_cols in groups.items():
            # Strip trailing separators from the head to get the clean file
            # stem, then split into staging directory and variant name.
            head_path = Path(head.rstrip("._- "))
            staging_dir = head_path.parent
            variant = head_path.name  # e.g. "render" from "/path/to/render"

            representations = [
                self._make_collection_representations(
                    col, staging_dir, variant)
                for col in group_cols
            ]

            product_name = get_product_name(
                project_name=self._context.data["projectName"],
                folder_entity=self._folder_entity,
                task_entity=self._task_entity,
                product_base_type=self._context.data["productBaseType"],
                product_type="render",
                host_name=self._context.data["hostName"],
                variant=variant,
            )

            instances.append(
                InstanceData(
                    publish=True,
                    active=True,
                    label="",
                    name=variant,
                    family="render",
                    families=["render", "review"],
                    folderPath=self._context.data["folderPath"],
                    task=self._context.data["task"],
                    variant=variant,
                    productBaseType=self._context.data["productBaseType"],
                    productName=product_name,
                    trait_representations=[
                        r.trait for r in representations],
                    standard_representations=[
                        r.standard for r in representations],
                )
            )

        return instances

    def _handle_reminders(
            self,
            path: Path,
            reminders: list[str]) -> list[InstanceData]:
        """Handle reminder files that are not part of any sequence.

        We'll do some fuzzy logic here - process the file name - if
        there is a common part at the beginning, collect them as multiple
        representations under one product version (one instance).

        If their names is completely different, we'll create separate
        instances for each of them.

        We create both trait-based representations and regular ones. For
        traits, we'll do some guessing for basic traits. Another plugin can
        add more, based on more sophisticated detection (for example using
        OpenImageIO tools, etc.)

        Args:
            path: root path for the reminder files
            reminders: list of reminder file names
                (not full paths, just names) that are not part
                of any sequence.

        Returns:
            list[InstanceData]: Created instances

        """
        if not reminders:
            return []

        # make reminders list with full paths
        reminder_paths = [(path / r) for r in reminders]

        stems = [Path(r).stem for r in reminder_paths]
        common_prefix = _common_stem_prefix(stems).rstrip("_-. ")

        if len(common_prefix) >= _MIN_PREFIX_LEN:
            # All files share a meaningful common prefix -> one instance
            # with multiple representations (one per file).

            representations = [
                self._make_representations(r)
                for r in reminder_paths
            ]

            product_name = get_product_name(
                project_name=self._context.data["projectName"],
                folder_entity=self._folder_entity,
                task_entity=self._task_entity,
                product_base_type=self._context.data["productBaseType"],
                product_type="render",
                host_name=self._context.data["hostName"],
                variant=self._context.data["productVariant"],
            )

            return [
                InstanceData(
                    publish=True,
                    active=True,
                    label="",
                    name=common_prefix,
                    family="render",
                    families=["render"],
                    folderPath=self._context.data["folderPath"],
                    task=self._context.data["task"],
                    variant=self._context.data["productVariant"],
                    productBaseType=self._context.data["productBaseType"],
                    productName=product_name,
                    trait_representations=[
                        r.trait for r in representations],
                    standard_representations=[
                        r.standard for r in representations
                    ],
                )
            ]
        # there is no correlation between the file names, create separate
        # instance for each of them
        instances = []
        for reminder_path in reminder_paths:
            representations = self._make_representations(
                reminder_path
            )

            product_name = get_product_name(
                project_name=self._context.data["projectName"],
                folder_entity=self._folder_entity,
                task_entity=self._task_entity,
                product_base_type=self._context.data["productBaseType"],
                product_type="render",
                host_name=self._context.data["hostName"],
                variant=self._context.data["productVariant"],
            )

            instances.append(
                InstanceData(
                    publish=True,
                    active=True,
                    label="Individual products",
                    name=representations.trait.name,
                    family="render",
                    families=["render", "review"],
                    folderPath=self._context.data["folderPath"],
                    task=self._context.data["task"],
                    variant=self._context.data["productVariant"],
                    productBaseType=self._context.data["productBaseType"],
                    productName=product_name,
                    trait_representations=[representations.trait],
                    standard_representations=[representations.standard],
                )
            )
        return instances

    def get_instances(self, path: Path) -> list[InstanceData]:
        """Get publishing instances from provided path.

        Path has to contain one file or a sequence of files.

        Args:
            path: Path

        Returns:
            list[InstanceData]: List of publishing instances.

        Raises:
            KnownPublishError: When file path is not a file or a sequence.

        """
        cols: list[clique.Collection] = []
        if path.is_file():
            # we'll use the same logic as if it is a single reminder
            rems = [path.name]
        else:
            files = list(path.glob("*"))
            if not files:
                msg = f"Provided path {path} has no files."
                raise KnownPublishError(msg)

            cols: list[clique.Collection]
            rems: list[str]
            cols, rems = clique.assemble(
                [f.as_posix() for f in files]
            )

        instances: list[InstanceData] = []

        # First, process reminders. This is just a list of file names.
        # We'll do some fuzzy logic here - process the file name - if
        # there is a common part at the beginning, collect them as multiple
        # representations under one product version (one instance).
        # If their names is completely different, we'll create separate
        # instances for each of them.
        if rems:
            instances = self._handle_reminders(path, rems)
        if cols:
            instances += self._handle_collections(cols)

        return instances
