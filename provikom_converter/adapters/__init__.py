"""Provikom Converter Adapters Package."""

from provikom_converter.adapters.base import (
    ArtifactFile,
    BackendAdapter,
    BuildOptions,
    BuildResult,
    ConversionArtifact,
    ConversionOptions,
    ConversionPlan,
    ConversionStep,
    MissingDependencyError,
    StagedDependency,
    UnsupportedRuntimeError,
)
from provikom_converter.adapters.cheerpj import CheerpJAdapter, select_cheerpj_runtime
from provikom_converter.adapters.swingjs import SwingJSAdapter
from provikom_converter.adapters.teavm import TeaVMAdapter

ALL_ADAPTERS = {
    "cheerpj": CheerpJAdapter(),
    "teavm": TeaVMAdapter(),
    "swingjs": SwingJSAdapter(),
}

__all__ = [
    "ArtifactFile",
    "BackendAdapter",
    "BuildOptions",
    "BuildResult",
    "ConversionArtifact",
    "ConversionOptions",
    "ConversionPlan",
    "ConversionStep",
    "MissingDependencyError",
    "StagedDependency",
    "UnsupportedRuntimeError",
    "CheerpJAdapter",
    "select_cheerpj_runtime",
    "TeaVMAdapter",
    "SwingJSAdapter",
    "ALL_ADAPTERS",
]
