from fastapi import APIRouter

from app.schemas.marked_image import MarkedImageRequest, MarkedImageResponse
from app.services.image_marker import build_marked_image

router = APIRouter()


@router.post(
    "/damage-summary-marked-image",
    response_model=MarkedImageResponse,
)
def damage_summary_marked_image(request: MarkedImageRequest) -> MarkedImageResponse:
    return build_marked_image(request)
