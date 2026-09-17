"""Serializable models used by the long-form analyzer and renderer."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SourceInfo:
    path: str
    name: str
    kind: str
    offset: float
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "SourceInfo":
        return cls(**value)


@dataclass(frozen=True)
class Scene:
    start: float
    end: float
    source: str
    scene_type: str
    zoom: float = 1.0
    pip_source: Optional[str] = None
    pip_position: Optional[str] = None
    secondary_source: Optional[str] = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Scene":
        return cls(**value)


@dataclass
class EditPlan:
    version: int
    episode: str
    seed: int
    common_start: float
    duration: float
    sources: List[SourceInfo]
    scenes: List[Scene]
    settings: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "EditPlan":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data["sources"] = [SourceInfo.from_dict(item) for item in data["sources"]]
        data["scenes"] = [Scene.from_dict(item) for item in data["scenes"]]
        return cls(**data)

    def source_by_name(self, name: str) -> SourceInfo:
        for source in self.sources:
            if source.name == name:
                return source
        raise KeyError(f"Source not present in edit plan: {name}")
