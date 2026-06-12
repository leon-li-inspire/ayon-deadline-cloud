"""Publishing Deadline Cloud Jobs."""
from __future__ import annotations

import contextlib
import logging
import os
import sys
from typing import Optional

import ayon_api
import pyblish.api
import pyblish.util
from ayon_core.addon import AddonsManager
from ayon_core.pipeline import install_ayon_plugins
from ayon_core.pipeline.publish import (
    filter_crashed_publish_paths,
    publish_plugins_discover,
)
from ayon_core.settings import get_project_settings

log = logging.getLogger(__name__)


def publish_content(  # noqa: PLR0913, PLR0917
        path: str,
        project_name: str,
        folder_path: str,
        user_name: str,
        variant: str,
        product_base_type: str,
        task_name: Optional[str] = None,
        host_name: Optional[str] = None,  # noqa: ARG001
        source_file: Optional[str] = None,
    ) -> None:
    """Publish content.

    This function bootstraps pyblish to run, collect the
    rendered files and publish them using appropriate pipeline.

    Args:
        path: Path to the folder where the content is to be published.
        project_name: Name of the project.
        folder_path: Path to the folder where the content is to be published.
        user_name: Name of the user who submitted the job.
        variant: Product variant.
        product_base_type: Product base type - passed to individual products.
        task_name: Name of the task to be published.
        host_name: Name of the host to be published.
        source_file: Path to the source file.

    Raises:
        ValueError: If the folder or task does not exist.
        RuntimeError: If the publishing process fails.

    """
    # Make public ayon api behave as other user
    # - this works only if public ayon api is using service user:
    # ayon-python-api does not have public api function to find
    # out if is used service user. So we need to have try-except.
    con = ayon_api.get_server_api_connection()
    with contextlib.suppress(ValueError):
        con.set_default_service_username(user_name)

    # check if folder exists
    folder_entity = ayon_api.get_folder_by_path(
        project_name=project_name,
        folder_path=folder_path,
    )
    if not folder_entity:
        msg = (
            f"Unable to find folder '{folder_path}' in "
            f"project '{project_name}'."
        )
        raise ValueError(msg)

    # check if task exists
    if task_name:
        task_entity = ayon_api.get_task_by_name(
            project_name=project_name,
            folder_id=folder_entity["id"],
            task_name=task_name,
        )
        if not task_entity:
            msg = (
                f"Unable to find task '{task_name}' in "
                f"folder '{folder_path}' in project '{project_name}'."
            )
            raise ValueError(msg)

    pyblish_context = pyblish.api.Context()
    pyblish_context.data["hostName"] = "shell"
    pyblish_context.data["projectName"] = project_name
    pyblish_context.data["folderPath"] = folder_path
    pyblish_context.data["outputPath"] = path
    # pyblish_context.data["taskEntity"] = task_entity
    pyblish_context.data["productVariant"] = variant
    pyblish_context.data["productBaseType"] = product_base_type

    if task_name:
        pyblish_context.data["task"] = task_name

    # if host_name:
    #     pyblish_context.data["hostName"] = host_name

    if source_file:
        pyblish_context.data["sourceFile"] = source_file

    pyblish.api.register_host("shell")
    pyblish.api.register_target("farm")

    install_ayon_plugins()
    project_settings = get_project_settings(project_name)
    addons_manager = AddonsManager(project_settings)

    applications_addon = addons_manager.get_enabled_addon("applications")
    if applications_addon is not None:
        env = applications_addon.get_farm_publish_environment_variables(
            project_name,
            folder_path,
            task_name,
        )
        os.environ.update(env)

    discover_result = publish_plugins_discover()

    filtered_crashed_paths = filter_crashed_publish_paths(
        project_name,
        set(discover_result.crashed_file_paths),
    )
    if filtered_crashed_paths:
        joined_paths = "\n".join(
            [f"- {path}" for path in filtered_crashed_paths]
        )
        log.error(
            "Plugin discovery strict mode is enabled. "
            "Crashed plugin paths that prevent from publishing:"
            "\n%s", joined_paths)
        sys.exit(1)

    publish_plugins = discover_result.plugins

    for result in pyblish.util.publish_iter(
            context=pyblish_context,
            plugins=publish_plugins,
    ):
        if result["error"]:
            raise RuntimeError(repr(result))
