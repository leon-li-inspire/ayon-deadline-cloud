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
        ("stub_submitter_mod:_StubAPI",),
    )
    try:
        obj = submitter_registry.get_submitter_api_for_host("maya")
        assert isinstance(obj, _StubAPI)
    finally:
        sys.modules.pop("stub_submitter_mod", None)


def test_import_map_values_are_tuples_of_specs():
    # Each host maps to an ordered tuple of "module.path:ClassName" candidates.
    for host, candidates in submitter_registry._SUBMITTER_API_IMPORTS.items():
        assert isinstance(candidates, tuple), host
        assert candidates, f"{host} has no candidate specs"
        for spec in candidates:
            assert spec.count(":") == 1, spec


def test_blender_tries_addon_name_first():
    # A real Blender install exposes the flat addon name; the deep source-tree
    # path is only a fallback. Order matters, so assert it.
    blender = submitter_registry._SUBMITTER_API_IMPORTS["blender"]
    assert blender[0].startswith("deadline_cloud_blender_submitter."), blender
    assert any(
        spec.startswith("deadline.blender_submitter.addons.") for spec in blender
    ), blender


def test_blender_prefers_new_submitter_over_legacy_api():
    # Blender renamed submitter_api:BlenderSubmitterAPI -> submitter:
    # BlenderSubmitter. The new module/class must be tried before the legacy
    # names so a rename-aware install binds to the new one.
    blender = submitter_registry._SUBMITTER_API_IMPORTS["blender"]
    first_new = next(
        i for i, spec in enumerate(blender) if spec.endswith(":BlenderSubmitter")
    )
    first_legacy = next(
        i for i, spec in enumerate(blender) if spec.endswith(":BlenderSubmitterAPI")
    )
    assert first_new < first_legacy, blender


def test_nuke_prefers_new_submitter_over_legacy_api():
    # Nuke renamed submitter_api:NukeSubmitterAPI -> submitter:NukeSubmitter
    # and removed the old module. The new module/class must be tried before the
    # legacy name so a rename-aware install binds to the new one.
    nuke = submitter_registry._SUBMITTER_API_IMPORTS["nuke"]
    first_new = next(
        i for i, spec in enumerate(nuke) if spec.endswith(":NukeSubmitter")
    )
    first_legacy = next(
        i for i, spec in enumerate(nuke) if spec.endswith(":NukeSubmitterAPI")
    )
    assert first_new < first_legacy, nuke


def test_get_submitter_api_falls_back_to_second_candidate(monkeypatch):
    # First candidate unimportable, second resolves -> second wins.
    stub_mod = types.ModuleType("stub_fallback_mod")

    class _StubAPI:
        pass

    stub_mod._StubAPI = _StubAPI
    sys.modules["stub_fallback_mod"] = stub_mod
    monkeypatch.setitem(
        submitter_registry._SUBMITTER_API_IMPORTS,
        "blender",
        (
            "nonexistent_first_choice.submitter_api:Nope",
            "stub_fallback_mod:_StubAPI",
        ),
    )
    try:
        obj = submitter_registry.get_submitter_api_for_host("blender")
        assert isinstance(obj, _StubAPI)
    finally:
        sys.modules.pop("stub_fallback_mod", None)


def test_get_submitter_api_raises_when_no_candidate_resolves(monkeypatch):
    monkeypatch.setitem(
        submitter_registry._SUBMITTER_API_IMPORTS,
        "blender",
        (
            "nope_one.submitter_api:A",
            "nope_two.submitter_api:B",
        ),
    )
    with pytest.raises(ModuleNotFoundError, match="Could not import the SubmitterAPI"):
        submitter_registry.get_submitter_api_for_host("blender")
