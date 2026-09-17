"""CAIVE long-form (16:9) video editing pipeline.

Analyzes synchronized webcam/screen recordings into a JSON edit plan, then
renders a 1920x1080 multi-camera edit with HyperFrames lower thirds, CTA
toasts, and animated frames.

This package is intentionally independent from ``stacked_script.stack`` so
that long-form work cannot change the existing Shorts rendering paths.
"""

from .models import EditPlan, Scene, SourceInfo

__all__ = ["EditPlan", "Scene", "SourceInfo"]

