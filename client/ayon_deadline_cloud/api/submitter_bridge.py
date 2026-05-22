"""Data classes for settings across the hosts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

from deadline.client.job_bundle.submission import AssetReferences

if TYPE_CHECKING:
    import pyblish.api
    from deadline.maya_submitter.data_classes import RenderSubmitterUISettings
    from deadline.nuke_submitter.data_classes import SubmitterUISettings
    from deadline_cloud_blender_submitter.template_filling import (
        BlenderSubmitterUISettings
    )


TSettings = TypeVar("TSettings")


@dataclass
class HoudiniSetting:
    """Data class for Houdini settings."""
    rop_node: Any = None
    input_filenames: set[str] = field(default_factory=set)
    output_directories: set[str] = field(default_factory=set)
    input_directories: set[str] = field(default_factory=set)


class SubmitterBridge(ABC, Generic[TSettings]):
    """Abstract base class for submitter bridge."""

    @property
    @abstractmethod
    def submitter_settings(self) -> TSettings:
        """Settings for the submitter UI."""
        ...

    @abstractmethod
    def get_job_template_for_submission(
            self,
            settings: TSettings,
            host_requirements: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Get the job template for submission.

        Args:
            settings: Settings for the submitter UI.
            host_requirements: Optional host requirements to include in the
                job template.

        Returns:
            dict[str, Any]: The job template for submission.
        """
        ...

    @abstractmethod
    def get_parameter_values_for_submission(
            self,
            settings: TSettings,
            queue_parameters: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """Get the parameter values for submission.

        Args:
            settings: Settings for the submitter UI.
            queue_parameters: Optional queue parameters to include in the
                parameter values.

        Returns:
            list[dict[str, Any]]: The parameter values for submission.
        """
        ...

    @abstractmethod
    def get_queue_parameters(
            self,
            farm_id: Optional[str] = None,
            queue_id: Optional[str] = None,
            initial_values: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Get queue parameters from Deadline Cloud.

        Args:
            farm_id: The farm ID. If not provided, uses the default from
                settings.
            queue_id: The queue ID. If not provided, uses the default from
                settings.
            initial_values: Optional dict of {parameter_name: value} to
                override default parameter values.

        Returns:
            A list of parameter definition dicts with "name" and "value" keys,
            suitable for passing to get_parameter_values_for_submission().

        Raises:
            DeadlineOperationError: If farm_id or queue_id are not configured.
        """
        ...

    @abstractmethod
    def get_asset_references_for_submission(
        self,
        asset_references: Optional[AssetReferences] = None,
    ) -> dict[str, Any]:
        """Get the asset references as a dictionary for render submissions.

        Args:
            asset_references: Optional AssetReferences object. If not
                provided, it will be constructed from the current scene or
                instance.

        Returns:
            The asset references dictionary ready for serialization.
        """
        ...


class MayaSubmitterBridge(SubmitterBridge["RenderSubmitterUISettings"]):
    """SubmitterBridge for Maya render submissions."""

    def __init__(self) -> None:
        """Initialize."""
        from deadline.maya_submitter.data_classes import (
            RenderSubmitterUISettings,
        )
        self._settings = RenderSubmitterUISettings()

    @property
    def submitter_settings(self) -> RenderSubmitterUISettings:
        """Get the submitter UI settings."""
        return self._settings

    def get_job_template_for_submission(  # noqa: PLR6301
            self,
            settings: RenderSubmitterUISettings,
            host_requirements: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Get the job template for Maya render submissions.

        Args:
            settings: The render submitter UI settings.
            host_requirements: Optional host requirements to inject into
                each job step.

        Returns:
            The job template dictionary ready for serialization.
        """
        from deadline.maya_submitter.maya_render_submitter import (
            get_job_template_for_submission,
        )
        return get_job_template_for_submission(
            settings=settings,
            host_requirements=host_requirements,
        )

    def get_parameter_values_for_submission(  # noqa: PLR6301
            self,
            settings: RenderSubmitterUISettings,
            queue_parameters: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """Get the parameter values for Maya render submissions.

        Args:
            settings: The render submitter UI settings.
            queue_parameters: Optional queue parameters to include.

        Returns:
            The parameter values list ready for serialization.
        """
        from deadline.maya_submitter.maya_render_submitter import (
            get_parameter_values_for_submission,
        )
        return get_parameter_values_for_submission(
            settings=settings,
            queue_parameters=queue_parameters,
        )

    def get_queue_parameters(  # noqa: PLR6301
            self,
            farm_id: Optional[str] = None,
            queue_id: Optional[str] = None,
            initial_values: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Get queue parameters from Deadline Cloud for Maya.

        Args:
            farm_id: Farm ID override; uses configured default if omitted.
            queue_id: Queue ID override; uses configured default if omitted.
            initial_values: Optional ``{name: value}`` overrides.

        Returns:
            Parameter definition dicts with ``name`` and ``value`` keys.
        """
        from deadline.maya_submitter.maya_render_submitter import (
            get_queue_parameters,
        )
        return get_queue_parameters(
            farm_id=farm_id,
            queue_id=queue_id,
            initial_values=initial_values,
        )

    def get_asset_references_for_submission(  # noqa: PLR6301
        self,
        asset_references: Optional[AssetReferences] = None,
    ) -> dict[str, Any]:
        """Get the asset references for Maya render submissions.

        Args:
            asset_references: Optional AssetReferences object. If not
                provided, an empty AssetReferences is used.

        Returns:
            The asset references dictionary ready for serialization.
        """
        from deadline.maya_submitter.maya_render_submitter import (
            get_asset_references_for_submission,
        )
        if asset_references is None:
            asset_references = AssetReferences()
        return get_asset_references_for_submission(
            asset_references=asset_references,
        )


class NukeSubmitterBridge(SubmitterBridge["SubmitterUISettings"]):
    """SubmitterBridge for Nuke render submissions."""

    def __init__(self) -> None:
        """Initialize."""
        from deadline.nuke_submitter.data_classes import SubmitterUISettings
        self._settings = SubmitterUISettings()

    @property
    def submitter_settings(self) -> SubmitterUISettings:
        """Get the submitter UI settings."""
        return self._settings

    def get_job_template_for_submission(  # noqa: PLR6301
            self,
            settings: SubmitterUISettings,
            host_requirements: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Get the job template for Nuke render submissions.

        Args:
            settings: The Nuke submitter UI settings.
            host_requirements: Optional host requirements to inject into
                each job step.

        Returns:
            The job template dictionary ready for serialization.
        """
        from deadline.nuke_submitter.deadline_submitter_for_nuke import (
            get_job_template_for_submission,
        )
        return get_job_template_for_submission(
            settings=settings,
            host_requirements=host_requirements,
        )

    def get_parameter_values_for_submission(  # noqa: PLR6301
            self,
            settings: SubmitterUISettings,
            queue_parameters: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """Get the parameter values for Nuke render submissions.

        Args:
            settings: The Nuke submitter UI settings.
            queue_parameters: Optional queue parameters to include.

        Returns:
            The parameter values list ready for serialization.
        """
        from deadline.nuke_submitter.deadline_submitter_for_nuke import (
            get_parameter_values_for_submission,
        )
        return get_parameter_values_for_submission(
            settings=settings,
            queue_parameters=queue_parameters,
        )

    def get_queue_parameters(  # noqa: PLR6301
            self,
            farm_id: Optional[str] = None,
            queue_id: Optional[str] = None,
            initial_values: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Get queue parameters from Deadline Cloud for Nuke.

        Args:
            farm_id: Farm ID override; uses configured default if omitted.
            queue_id: Queue ID override; uses configured default if omitted.
            initial_values: Optional ``{name: value}`` overrides.

        Returns:
            Parameter definition dicts with ``name`` and ``value`` keys.
        """
        from deadline.nuke_submitter.deadline_submitter_for_nuke import (
            get_queue_parameters,
        )
        return get_queue_parameters(
            farm_id=farm_id,
            queue_id=queue_id,
            initial_values=initial_values,
        )

    def get_asset_references_for_submission(  # noqa: PLR6301
        self,
        asset_references: Optional[AssetReferences] = None,
    ) -> dict[str, Any]:
        """Get the asset references for Nuke render submissions.

        Args:
            asset_references: Optional AssetReferences object. If not
                provided, it is collected from the current Nuke scene.

        Returns:
            The asset references dictionary ready for serialization.
        """
        from deadline.nuke_submitter.assets import (
            get_scene_asset_references,
        )

        return get_scene_asset_references().asset_references.to_dict()


class HoudiniSubmitterBridge(SubmitterBridge["HoudiniSetting"]):
    """SubmitterBridge for Houdini render submissions."""

    def __init__(
            self,
            instance: Optional[pyblish.api.Instance] = None,
    ) -> None:
        """Initialize.

        Args:
            instance: Optional Pyblish instance. When provided, the ROP node
                and file lists are read from it automatically.
        """
        self._settings = HoudiniSetting()
        if instance is not None:
            self._init_from_instance(instance)

    def _init_from_instance(
            self, instance: pyblish.api.Instance
    ) -> None:
        """Populate settings from a Pyblish instance."""
        import hou  # type: ignore[import]

        rop_node = hou.node(instance.data.get("instance_node"))
        self._settings.rop_node = rop_node
        self._settings.input_filenames = {
            n.unexpandedString()
            for n in rop_node.parm("input_filenames").multiParmInstances()
        }
        self._settings.input_directories = {
            n.unexpandedString()
            for n in rop_node.parm("input_directories").multiParmInstances()
        }
        self._settings.output_directories = {
            n.unexpandedString()
            for n in rop_node.parm("output_directories").multiParmInstances()
        }

    @property
    def submitter_settings(self) -> HoudiniSetting:
        """Get the submitter UI settings."""
        return self._settings

    def get_job_template_for_submission(  # noqa: PLR6301
            self,
            settings: HoudiniSetting,
            host_requirements: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Get the job template for Houdini render submissions.

        Args:
            settings: The Houdini submitter settings.
            host_requirements: Optional host requirements to inject into
                each job step.

        Returns:
            The job template dictionary ready for serialization.
        """
        from deadline_cloud_for_houdini.submitter import (  # type: ignore[import]
            get_job_template_for_submission,
        )
        return get_job_template_for_submission(
            settings=settings,
            host_requirements=host_requirements,
        )

    def get_parameter_values_for_submission(  # noqa: PLR6301
            self,
            settings: HoudiniSetting,
            queue_parameters: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """Get the parameter values for Houdini render submissions.

        Args:
            settings: The Houdini submitter settings.
            queue_parameters: Optional queue parameters to include.

        Returns:
            The parameter values list ready for serialization.
        """
        from deadline_cloud_for_houdini.submitter import (  # type: ignore[import]
            get_parameter_values_for_submission,
        )
        return get_parameter_values_for_submission(
            settings=settings,
            queue_parameters=queue_parameters,
        )

    def get_queue_parameters(  # noqa: PLR6301
            self,
            farm_id: Optional[str] = None,
            queue_id: Optional[str] = None,
            initial_values: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Get queue parameters from Deadline Cloud for Houdini.

        Args:
            farm_id: Farm ID override; uses configured default if omitted.
            queue_id: Queue ID override; uses configured default if omitted.
            initial_values: Optional ``{name: value}`` overrides.

        Returns:
            Parameter definition dicts with ``name`` and ``value`` keys.
        """
        from deadline_cloud_for_houdini.submitter import (  # type: ignore[import]
            get_queue_parameters,
        )
        return get_queue_parameters(
            farm_id=farm_id,
            queue_id=queue_id,
            initial_values=initial_values,
        )

    def get_asset_references_for_submission(
        self,
        asset_references: Optional[AssetReferences] = None,
    ) -> dict[str, Any]:
        """Get the asset references for Houdini render submissions.

        Args:
            asset_references: Optional AssetReferences object. If not
                provided, one is constructed from the current settings.

        Returns:
            The asset references dictionary ready for serialization.
        """
        from deadline_cloud_for_houdini.submitter import (  # type: ignore[import]
            get_asset_references_for_submission,
        )
        if asset_references is None:
            asset_references = AssetReferences(
                input_filenames=set(
                    self._settings.input_filenames or set()
                ),
                input_directories=set(
                    self._settings.input_directories or set()
                ),
                output_directories=set(
                    self._settings.output_directories or set()
                ),
            )
        return get_asset_references_for_submission(
            asset_references=asset_references,
        )


class BlenderSubmitterBridge(SubmitterBridge["BlenderSubmitterUISettings"]):
    """SubmitterBridge for Blender render submissions."""

    def __init__(self) -> None:
        """Initialize."""
        from deadline_cloud_blender_submitter.template_filling import (
            BlenderSubmitterUISettings
        )
        self._settings = BlenderSubmitterUISettings()

    @property
    def submitter_settings(self) -> BlenderSubmitterUISettings:
        """Get the submitter UI settings."""
        return self._settings

    def get_job_template_for_submission(  # noqa: PLR6301
            self,
            settings: BlenderSubmitterUISettings,
            host_requirements: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Get the job template for Blender render submissions.

        Args:
            settings: The Blender submitter UI settings.
            host_requirements: Optional host requirements to inject into
                each job step.

        Returns:
            The job template dictionary ready for serialization.
        """
        from deadline_cloud_blender_submitter.template_filling import (
            get_job_template_for_submission,
        )
        return get_job_template_for_submission(
            settings=settings,
            host_requirements=host_requirements,
        )

    def get_parameter_values_for_submission(  # noqa: PLR6301
            self,
            settings: BlenderSubmitterUISettings,
            queue_parameters: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """Get the parameter values for Blender render submissions.

        Args:
            settings: The Blender submitter UI settings.
            queue_parameters: Optional queue parameters to include.

        Returns:
            The parameter values list ready for serialization.
        """
        from deadline_cloud_blender_submitter.template_filling import (
            get_parameter_values_for_submission,
        )
        return get_parameter_values_for_submission(
            settings=settings,
            queue_parameters=queue_parameters,
        )

    def get_queue_parameters(  # noqa: PLR6301
            self,
            farm_id: Optional[str] = None,
            queue_id: Optional[str] = None,
            initial_values: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Get queue parameters from Deadline Cloud for Blender.

        Args:
            farm_id: Farm ID override; uses configured default if omitted.
            queue_id: Queue ID override; uses configured default if omitted.
            initial_values: Optional ``{name: value}`` overrides.

        Returns:
            Parameter definition dicts with ``name`` and ``value`` keys.
        """
        from deadline_cloud_blender_submitter.template_filling import (
            get_queue_parameters,
        )
        return get_queue_parameters(
            farm_id=farm_id,
            queue_id=queue_id,
            initial_values=initial_values,
        )

    def get_asset_references_for_submission(  # noqa: PLR6301
        self,
        asset_references: Optional[AssetReferences] = None,
    ) -> dict[str, Any]:
        """Get the asset references for Blender render submissions.

        Args:
            asset_references: Optional AssetReferences object. If not
                provided, it is collected from the current Blender scene.

        Returns:
            The asset references dictionary ready for serialization.
        """
        from deadline_cloud_blender_submitter.template_filling import (
            get_asset_references_for_submission,
        )
        if asset_references is None:
            asset_references = AssetReferences()
        return get_asset_references_for_submission(
            asset_references=asset_references,
        )


def get_submitter_bridge(
        host_name: str, instance: pyblish.api.Instance
    ) -> SubmitterBridge:
    """Get the appropriate submitter bridge for the given host.

    Args:
        host_name (str): The name of the host application.
        instance (pyblish.api.Instance): The Pyblish instance.

    Returns:
        SubmitterBridge: The submitter bridge for the specified host.

    Raises:
        NotImplementedError: If the host is not supported.
    """
    if host_name == "maya":
        return MayaSubmitterBridge()

    if host_name == "houdini":
        return HoudiniSubmitterBridge(instance=instance)

    if host_name == "nuke":
        return NukeSubmitterBridge()

    if host_name == "blender":
        return BlenderSubmitterBridge()

    msg = f"Unsupported host: {host_name}"
    raise NotImplementedError(msg)
