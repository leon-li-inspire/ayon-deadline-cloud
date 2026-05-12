"""Data classes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from ayon_core.pipeline.traits import Representation as TraitRepresentation


@dataclass
class StandardRepresentation:
    """Representation dataclass."""
    name: str
    ext: str
    files: Union[str, list[str]]
    stagingDir: str


@dataclass
class InstanceData:
    """Instance dataclass."""
    publish: bool
    active: bool
    label: str
    name: str
    productName: str
    productBaseType: str
    family: str
    families: list[str]
    folderPath: str
    task: str
    variant: str
    standard_representations: list[StandardRepresentation]
    trait_representations: list[TraitRepresentation]
