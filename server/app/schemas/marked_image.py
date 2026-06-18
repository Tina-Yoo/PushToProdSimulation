from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class DamageSectionInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    section_no: Optional[int] = None
    damage_item_id: Optional[str] = None
    panel: Optional[str] = None
    panel_label: Optional[str] = None
    damage_type_labels: List[str] = []
    confidence_percent: Optional[int] = None
    requires_review: bool = False
    included_in_estimate: bool = True


class MarkedImageRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    estimate_id: Optional[str] = None
    damage_sections: List[DamageSectionInput] = []


class MarkerInfo(BaseModel):
    marker_no: int
    damage_item_id: Optional[str] = None
    panel: Optional[str] = None
    panel_label: Optional[str] = None
    damage_type_labels: List[str] = []
    confidence_percent: Optional[int] = None
    requires_review: bool = False
    included_in_estimate: bool = True
    status: str
    x_percent: float
    y_percent: float


class MarkedImageResponse(BaseModel):
    filename: str
    content_type: str = "image/png"
    data: str
    marker_count: int
    markers: List[MarkerInfo] = []
