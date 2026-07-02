"""Tests for ayon_deadline_cloud.api.submitter_registry."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# Load submitter_registry.py directly by file path. Importing the
# `ayon_deadline_cloud` package would run its __init__ -> addon.py, which pulls
# in `ayon_core` (only present inside a running AYON host), so we bypass it.
_REG_PATH = (
    Path(__file__).resolve().parents[1]
    / "ayon_deadline_cloud"
    / "api"
    / "submitter_registry.py"
)
_spec = importlib.util.spec_from_file_location(
    "ayon_deadline_cloud_submitter_registry_under_test", _REG_PATH
)
submitter_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(submitter_registry)


def test_supported_hosts_are_the_validated_four():
    # Only the DCCs validated end-to-end are exposed; cinema4d/vred/max/
    # unreal/keyshot were removed as not-yet-supported per review.
    assert set(submitter_registry.SUPPORTED_HOSTS) == {
        "maya",
        "nuke",
        "blender",
        "houdini",
    }


def test_supported_hosts_matches_import_map():
    assert set(submitter_registry.SUPPORTED_HOSTS) == set(
        submitter_registry._SUBMITTER_API_IMPORTS
    )


@pytest.mark.parametrize("host", ["cinema4d", "vred", "max", "unreal", "keyshot"])
def test_removed_hosts_absent(host):
    assert host not in submitter_registry._SUBMITTER_API_IMPORTS


def test_unknown_host_raises_valueerror():
    with pytest.raises(ValueError, match="No SubmitterAPI mapping"):
        submitter_registry.get_submitter_api_for_host("not_a_dcc")


def test_get_submitter_api_imports_and_instantiates(monkeypatch):
    # Point a host at a stub module/class and confirm it's imported + built.
    stub_mod = types.ModuleType("stub_submitter_mod")

    class _StubAPI:
        pass

    stub_mod._StubAPI = _StubAPI
    sys.modules["stub_submitter_mod"] = stub_mod
    monkeypatch.setitem(
        submitter_registry._SUBMITTER_API_IMPORTS,
        "maya",
        "stub_submitter_mod:_StubAPI",
    )
    try:
        obj = submitter_registry.get_submitter_api_for_host("maya")
        assert isinstance(obj, _StubAPI)
    finally:
        sys.modules.pop("stub_submitter_mod", None)
