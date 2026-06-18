import type {
  HealthResponse,
  SkrSlotClsResponse,
  SkrEstimateResponse,
  ExtractStructuredCommentClaimsResponse,
  StructuredClaim,
  CommentImageComparisonResponse,
  ClaudeVisionCheckRequest,
  ClaudeVisionCheckResult,
  FinalSummarizedResultRequest,
  FinalSummarizedResultResponse,
} from "@/types/api";
import estimateTypeMatch from "@/asset/estimateTypeMatch.json";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://112.220.206.226:8100";
const COMMENT_API_BASE_URL =
  import.meta.env.VITE_COMMENT_API_BASE_URL ?? "http://172.16.10.176:5180";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

// ============ Mapping Constants ============
// 슬롯 분류 매핑 (하드코딩 - SKR API 전용)
export const CATEGORY_MAP: Record<string, string> = {
  front_center: "정면(중앙)",
  front_driver: "정면(운전석)",
  front_passenger: "정면(동승석)",
  side_left: "측면(좌)",
  side_right: "측면(우)",
  rear_center: "후면(중앙)",
  rear_driver: "후면(운전석)",
  rear_passenger: "후면(동승석)",
  other: "기타",
  non_vehicle: "비차량",
};

// estimateTypeMatch.json 기반 매핑
export const DAMAGE_TYPE_MAP: Record<string, string> = Object.fromEntries(
  estimateTypeMatch.damageTypes.map((d) => [d.code, d.name])
);

export const PANEL_NAME_MAP: Record<string, string> = Object.fromEntries(
  estimateTypeMatch.panelTypes.map((p) => [p.code, p.name])
);

export const PANEL_COLOR_MAP: Record<string, string> = Object.fromEntries(
  estimateTypeMatch.panelTypes.map((p) => [p.code, p.color])
);

export const REPAIR_TYPE_MAP: Record<string, string> = Object.fromEntries(
  estimateTypeMatch.repairTypes.map((r) => [r.code, r.name])
);

// ============ Error Class ============
export class CarVisionApiError extends Error {
  statusCode?: number;

  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = "CarVisionApiError";
    this.statusCode = statusCode;
  }
}

// ============ SSE Helper ============
async function consumeSSE<T>(
  url: string,
  options: RequestInit,
  onProgress?: (message: string) => void
): Promise<T> {
  const response = await fetch(url, options);

  if (!response.ok) {
    throw new CarVisionApiError(
      `HTTP ${response.status}: ${response.statusText}`,
      response.status
    );
  }

  if (!response.body) {
    throw new CarVisionApiError("No response body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: T | null = null;
  const receivedEvents: string[] = [];

  // SSE 파싱: event와 data를 쌍으로 저장
  let currentEvent: string | null = null;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        // Process any remaining data in buffer
        if (buffer.trim()) {
          console.log("Remaining buffer:", buffer);
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmedLine = line.trim();

        // 빈 줄이나 주석은 스킵
        if (!trimmedLine || trimmedLine.startsWith(":")) {
          continue;
        }

        // event: 라인 처리
        if (trimmedLine.startsWith("event:")) {
          currentEvent = trimmedLine.slice(6).trim();
          receivedEvents.push(currentEvent);
          continue;
        }

        // data: 라인 처리
        if (trimmedLine.startsWith("data:")) {
          const data = trimmedLine.slice(5).trim();

          if (currentEvent === "progress") {
            onProgress?.(data);
          } else if (currentEvent === "complete") {
            try {
              result = JSON.parse(data) as T;
              console.log("Successfully parsed complete event");
            } catch (parseError) {
              console.error("Failed to parse complete data:", data);
              throw new CarVisionApiError("Failed to parse SSE complete data");
            }
          } else if (currentEvent === "error") {
            throw new CarVisionApiError(`SSE error event: ${data}`);
          }

          // Reset current event after processing
          currentEvent = null;
        }
      }
    }
  } catch (error) {
    reader.releaseLock();
    if (error instanceof CarVisionApiError) {
      throw error;
    }
    throw new CarVisionApiError(`SSE stream error: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    reader.releaseLock();
  }

  if (!result) {
    console.error("Received events:", receivedEvents);
    throw new CarVisionApiError(
      `SSE stream ended without complete event. Received events: ${receivedEvents.join(", ") || "none"}`
    );
  }

  return result;
}

// ============ API Functions ============

export async function checkHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) {
    throw new CarVisionApiError(
      `Health check failed: ${response.statusText}`,
      response.status
    );
  }
  return response.json();
}

export async function classifyCarSlots(
  images: File[],
  vehicleCategory?: string,
  onProgress?: (message: string) => void
): Promise<SkrSlotClsResponse> {
  const formData = new FormData();
  images.forEach((img) => formData.append("images", img));
  if (vehicleCategory) {
    formData.append("vehicle_category", vehicleCategory);
  }

  return consumeSSE<SkrSlotClsResponse>(
    `${API_BASE_URL}/api/v1/skrentalcar/exterior-damage/slot-cls`,
    {
      method: "POST",
      headers: {
        access_token: API_KEY,
      },
      body: formData,
    },
    onProgress
  );
}

export async function estimateExteriorDamage(
  images: File[],
  vehicleCategory?: string,
  requestId?: string,
  onProgress?: (message: string) => void
): Promise<SkrEstimateResponse> {
  const formData = new FormData();
  images.forEach((img) => formData.append("images", img));
  if (vehicleCategory) {
    formData.append("vehicle_category", vehicleCategory);
  }
  if (requestId) {
    formData.append("request_id", requestId);
  }
  formData.append("return_detail_visualization", "true");

  return consumeSSE<SkrEstimateResponse>(
    `${API_BASE_URL}/api/v1/skrentalcar/exterior-damage/estimate`,
    {
      method: "POST",
      headers: {
        access_token: API_KEY,
      },
      body: formData,
    },
    onProgress
  );
}

export async function extractStructuredCommentClaims(
  comment: string,
  estimateId?: string
): Promise<ExtractStructuredCommentClaimsResponse> {
  const response = await fetch(
    `${COMMENT_API_BASE_URL}/api/v1/extract-structured-comment-claims`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        estimate_id: estimateId ?? null,
        comment,
      }),
    }
  );

  if (!response.ok) {
    throw new CarVisionApiError(
      `Extract comment claims failed: ${response.statusText}`,
      response.status
    );
  }

  return response.json();
}

export async function commentImageComparison(
  exteriorDamageEstimate: SkrEstimateResponse,
  claims: StructuredClaim[],
  comment?: string | null,
  estimateId?: string | null
): Promise<CommentImageComparisonResponse> {
  const response = await fetch(
    `${COMMENT_API_BASE_URL}/api/v1/comment-image-comparison-result`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        estimate_id: estimateId ?? null,
        comment: comment ?? null,
        claims,
        exterior_damage_estimate: exteriorDamageEstimate,
      }),
    }
  );

  if (!response.ok) {
    throw new CarVisionApiError(
      `Comment-image comparison failed: ${response.statusText}`,
      response.status
    );
  }

  return response.json();
}

export async function claudeVisionCheck(
  request: ClaudeVisionCheckRequest
): Promise<ClaudeVisionCheckResult> {
  const response = await fetch(
    `${COMMENT_API_BASE_URL}/api/v1/claude-vision-check-result`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    }
  );

  if (!response.ok) {
    throw new CarVisionApiError(
      `Claude vision check failed: ${response.statusText}`,
      response.status
    );
  }

  return response.json();
}

export async function finalSummarizedResult(
  request: FinalSummarizedResultRequest
): Promise<FinalSummarizedResultResponse> {
  const response = await fetch(
    `${COMMENT_API_BASE_URL}/api/v1/final-summarized-result`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    }
  );

  if (!response.ok) {
    throw new CarVisionApiError(
      `Final summarized result failed: ${response.statusText}`,
      response.status
    );
  }

  return response.json();
}
