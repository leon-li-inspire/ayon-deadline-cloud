"""Tests for ayon_deadline_cloud.api.environment."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# Load environment.py directly by file path. Importing the `ayon_deadline_cloud`
# package would run its __init__ -> addon.py, which pulls in `ayon_core` (only
# present inside a running AYON host), so we bypass it.
_ENV_PATH = (
    Path(__file__).resolve().parents[1]
    / "ayon_deadline_cloud"
    / "api"
    / "environment.py"
)
_spec = importlib.util.spec_from_file_location(
    "ayon_deadline_cloud_environment_under_test", _ENV_PATH
)
environment = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(environment)


def test_blender_version_modules_prefers_addon_name():
    # The flat addon name (real Blender install) is tried before the deep
    # source-tree path. Order matters, so assert it.
    modules = environment._BLENDER_VERSION_MODULES
    assert modules[0] == "deadline_cloud_blender_submitter._version"
    assert any(m.startswith("deadline.blender_submitter.addons.") for m in modules)


def test_import_blender_adaptor_version_falls_back(monkeypatch):
    # First candidate unimportable, second resolves -> second wins.
    stub_mod = types.ModuleType("stub_blender_version_mod")
    stub_mod.version_tuple = (4, 2, 0)
    sys.modules["stub_blender_version_mod"] = stub_mod
    monkeypatch.setattr(
        environment,
        "_BLENDER_VERSION_MODULES",
        ("nonexistent_first_choice._version", "stub_blender_version_mod"),
    )
    try:
        assert environment._import_blender_adaptor_version_tuple() == (4, 2, 0)
    finally:
        sys.modules.pop("stub_blender_version_mod", None)


def test_import_blender_adaptor_version_raises_when_none_resolve(monkeypatch):
    monkeypatch.setattr(
        environment,
        "_BLENDER_VERSION_MODULES",
        ("nope_one._version", "nope_two._version"),
    )
    with pytest.raises(
        ModuleNotFoundError, match="Could not import the Blender submitter _version"
    ):
        environment._import_blender_adaptor_version_tuple()
