"""Provikom Converter Adapters Package."""

from provikom_converter.adapters.base import (
    ArtifactFile,
    BackendAdapter,
    ConversionArtifact,
    ConversionOptions,
    ConversionPlan,
    ConversionStep,
)
from provikom_converter.adapters.cheerpj import CheerpJAdapter
from provikom_converter.adapters.swingjs import SwingJSAdapter
from provikom_converter.adapters.teavm import TeaVMAdapter

ALL_ADAPTERS = [
    CheerpJAdapter(),
    TeaVMAdapter(),
    SwingJSAdapter(),
]

__all__ = [
    "ArtifactFile",
    "BackendAdapter",
    "ConversionArtifact",
    "ConversionOptions",
    "ConversionPlan",
    "ConversionStep",
    "CheerpJAdapter",
    "TeaVMAdapter",
    "SwingJSAdapter",
    "ALL_ADAPTERS",
]
