"""Deadline Cloud Addon for AYON."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import click
from ayon_core.addon import AYONAddon, IPluginPaths, click_wrap

from ayon_deadline_cloud.api.publish import publish_content

from .version import __version__

if TYPE_CHECKING:
    from logging import Logger

DEADLINE_CLOUD_ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))


class DeadlineCloudAddon(AYONAddon, IPluginPaths):
    """Deadline Cloud Addon for AYON."""
    name = "deadline_cloud"
    version = __version__
    log: Logger

    @staticmethod
    def add_implementation_envs(
        env: dict[str, str], _app: Any) -> None:  # noqa: ANN401
        """Add environment variables for the addon implementation.

        Args:
            env: Dictionary of environment variables to be updated with
                implementation specific variables.
            _app: Name of the host application to add specific environment
                variables for.

        """
        # TODO(antirotor): Implement this env variable to set AYON scoped
        # Deadline Cloud configuration file path for the client to use.
        # env["DEADLINE_CONFIG_FILE_PATH"] = ...

    def get_publish_plugin_paths(  # noqa: PLR6301
            self,
            host_name: str,
    ) -> list[str]:  # ty:ignore[invalid-method-override]
        """Return list of paths to publish plugins.

        Args:
            host_name: Optional name of the host application
                to get specific plugin paths.

        Returns:
            List of paths to publish plugins.

        """
        return [os.path.join(
            DEADLINE_CLOUD_ADDON_ROOT, "plugins", "publish")]

    def get_create_plugin_paths(  # noqa: PLR6301
            self,
            host_name: str,
    ) -> list[str]:
        """Return list of paths to creator plugins.

        Args:
            host_name: Optional name of the host application
                to get specific plugin paths.

        Returns:
            List of paths to creator plugins.

        """
        return [os.path.join(
            DEADLINE_CLOUD_ADDON_ROOT,
            "plugins", "create", host_name or "global")]

    def _publish(  # noqa: PLR0913, PLR0917
            self,
            path: str,
            folder_path: str,
            project_name: str,
            user_name: str,
            product_base_type: str,
            variant: str,
            task_name: Optional[str],
            host_name: Optional[str],
            source_file: Optional[str],
            path_mapping_file: Optional[str],
    ) -> None:
        """Publish the result of a Deadline Cloud processed job.

        Args:
            path: Path to the folder containing the job
                result to publish.
            folder_path: Folder path for the context on AYON.
            project_name: Name of the project associated with the job result.
            user_name: Name of the user who submitted the job.
            product_base_type: Base name of the product to publish.
                Note that currently it is overridden down the line
                with hardcoded `render` - in the future, product base type
                should be passed correctly to support other publish
                types.
            variant: Product variant.
            task_name: Optional name of the task associated with
                the job result.
            host_name: Optional name of the host application associated with
                the job result.
            source_file: Optional path to a source file related to the job
                result, which might be used for validation or as part of
                the publishing process.
            path_mapping_file: Optional path to a file containing path mapping
                rules, which can be used to resolve file paths during
                the publishing process.

        """
        self.log.debug(
            "publish called with arguments: "
            "folder_path=%s, project_name=%s, "
            "user_name=%s, product_base_name=%s, task_name=%s, "
            "host_name=%s, source_file=%s, variant=%s",
            folder_path, project_name, user_name,
            product_base_type, task_name, host_name, source_file,
            variant
        )

        # This is simple remapping code to take the path specified in the job
        # and remap it to current system. Deadline Cloud won't do it
        # automatically, because the path isn't of PATH type (it can't be
        # because of the restriction in OpenJD that paths must be relative
        # to the job bundle. This remapping is very basic and is based on
        # simple string replacement - we need to eventually replace it with
        # something more robust, or force somehow Deadline Cloud to do it.

        if path_mapping_file:
            self.log.debug("Using path mapping file: %s", path_mapping_file)
            with open(path_mapping_file, encoding="utf8") as f:
                path_mapping = json.load(f)

            for rules in path_mapping["path_mapping_rules"]:
                if path.startswith(rules["source_path"]):
                    path = path.replace(
                        rules["source_path"],
                        f'{rules["destination_path"]}{os.path.sep}',
                        1
                    )
                    if os.path.sep == "/":
                        path = path.replace("\\", "/")

                    path = Path(path).resolve().as_posix()
                    self.log.debug(
                        "Mapped path to: %s using rules: %s",
                        path, rules
                    )
                    break

        publish_content(
            path=path,
            project_name=project_name,
            folder_path=folder_path,
            product_base_type=product_base_type,
            variant=variant,
            user_name=user_name,
            task_name=task_name,
            host_name=host_name,
            source_file=source_file,
        )

    def _cli_main(self) -> None:
        """Add CLI commands to this addon."""

    def cli(self, addon_click_group: click.Group) -> None:
        """CLI interface.

        Args:
            addon_click_group: Click group to add commands to.

        """
        cli_main = click_wrap.group(
            self._cli_main,
            name=self.name,
            help="Deadline Cloud commands",
        )

        cli_main.command(
            self._publish,
            name="publish",
            help=(
                "Publish the result of a Deadline Cloud "
                "processed job."
            ),
        ).option(
            "-f",
            "--folder-path",
            type=click.STRING,
            required=True,
        ).option(
            "-t",
            "--task-name",
            type=click.STRING,
            required=False,
        ).option(
            "-p",
            "--project-name",
            type=click.STRING,
            required=True,
        ).option(
            "-u",
            "--user-name",
            type=click.STRING,
            required=True,
        ).option(
            "--host-name",
            type=click.STRING,
            required=False,
        ).option(
            "--product-base-type",
            type=click.STRING,
            required=True
        ).option(
            "-s",
            "--source-file",
            type=click.Path(exists=False, file_okay=True, dir_okay=False),
        ).option(
            "--path-mapping-file",
            type=click.Path(exists=True, file_okay=True, dir_okay=False),
            required=False,
        ).argument(
            "path",
            nargs=1,
            type=click.Path(exists=False, file_okay=False, dir_okay=True),
        )

        addon_click_group.add_command(cli_main.to_click_obj())
