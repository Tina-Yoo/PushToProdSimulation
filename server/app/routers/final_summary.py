from fastapi import APIRouter

from app.schemas.final_summary import FinalSummaryRequest, FinalSummaryResponse
from app.services.final_summary_builder import build_final_summary

router = APIRouter()


@router.post(
    "/final-summarized-result",
    response_model=FinalSummaryResponse,
)
def final_summarized_result(request: FinalSummaryRequest) -> FinalSummaryResponse:
    return build_final_summary(request)
