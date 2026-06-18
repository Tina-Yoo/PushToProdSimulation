# ObiVision — AI 차량 파손 검수 앱 빌드 가이드

이 스킬을 실행하면 Claude Code가 ObiVision 앱을 처음부터 완성까지 빌드합니다.
ObiVision은 차량 파손 사진을 업로드하면 AI가 손상을 탐지하고 수리 견적을 자동 생성하는 웹앱입니다.

---

## 1. 프로젝트 초기화

다음 명령을 실행하세요:

```bash
npm create vite@latest obivision -- --template react-ts
cd obivision
npm install
```

의존성 설치:

```bash
npm install wouter
npm install tailwindcss @tailwindcss/vite
npm install @radix-ui/react-dialog @radix-ui/react-select @radix-ui/react-tooltip @radix-ui/react-slot
npm install lucide-react
npm install class-variance-authority clsx tailwind-merge
npm install @tanstack/react-query
npm install @react-pdf/renderer
```

shadcn/ui 초기화:

```bash
npx shadcn@latest init
```

선택: TypeScript, Tailwind CSS v4, `src/` 경로, import alias `@/*`.

---

## 2. 기술 스택

| 영역 | 선택 | 이유 |
|------|------|------|
| 프레임워크 | React 19 + Vite | 빠른 개발, 최신 React |
| 언어 | TypeScript | 타입 안전성 |
| 스타일 | Tailwind CSS v4 | 유틸리티 클래스, shadcn 통합 |
| 컴포넌트 | shadcn/ui | 접근성, 커스터마이징 |
| 라우팅 | wouter | 경량, React Router 불필요 |
| 상태 | React Context + useReducer | 서버 없음, 클라이언트 전용 |
| PDF | @react-pdf/renderer | 한국어 지원, 레이아웃 안정 |
| HTTP | native fetch | axios 불필요 |

**중요**: React Router 사용 금지. 반드시 `wouter`를 사용하세요.

---

## FE 역할 원칙 (필수)

**FE는 서버에서 받은 데이터를 그대로 표시하는 역할만 합니다.**

클라이언트 사이드에서 어떤 분석이나 계산도 수행하지 않습니다.
신뢰도 점수 계산, 코멘트 일치 분석, 가격 산정 등 **모든 분석과 계산은 AI 서버에서 진행**됩니다.

FE가 해야 할 것:
- API 응답 데이터를 상태에 저장
- 저장된 데이터를 화면에 렌더링
- 사용자 입력을 API 요청 파라미터로 전달

FE가 하면 안 되는 것:
- confidence 점수 계산 (severity → 숫자 변환 등)
- 키워드 기반 코멘트 일치 분석
- 수리 단가 직접 계산
- 신뢰도/점수 직접 산출

---

## 3. 사용자 플로우

```
/ (홈)
  → /request (견적 요청)
      1. 차량 선택 (드롭다운)
      2. 사진 업로드 → AI 앵글 자동 분류
      3. 분류된 사진 확인 (4x그리드)
      4. 전체 코멘트 입력 (선택) — 하나의 텍스트 영역
      → [요청하기] → AI 분석 모달 (5단계 진행 표시)
          → /result (견적 결과)
              손상 섹션별 아코디언 + 근거 사진 확대
              → [견적서 내보내기] → 견적서 미리보기 모달 (2탭) → PDF 저장
```

---

## 4. 디렉토리 구조

```
src/
├── App.tsx
├── main.tsx
├── index.css
├── pages/
│   ├── Home.tsx
│   ├── QuoteRequest.tsx
│   └── QuoteResult.tsx
├── components/
│   ├── QuoteExportModal.tsx
│   └── ui/                    ← shadcn 컴포넌트
├── store/
│   └── QuoteContext.tsx
├── services/
│   └── carVisionApi.ts
├── hooks/
│   └── useImageZoom.ts
├── types/
│   └── api.ts
├── utils/
│   └── QuotePdfDocument.tsx
└── lib/
    └── utils.ts
```

---

## 5. 핵심 데이터 모델

`src/store/QuoteContext.tsx`에 구현하세요.

```typescript
import type { FinalSummarizedResultResponse } from "@/types/api";

interface UploadedPhoto {
  id: string;
  file?: File;
  preview: string;           // URL.createObjectURL()
  category: string;          // AI 분류 결과 (예: "정면(중앙)")
  damageOverlay?: string;    // base64 PNG, SKR estimate API에서 반환
}

interface QuoteState {
  vehicleName: string;
  requestDate: string;       // YYYY.MM.DD
  photos: UploadedPhoto[];
  customerComment: string;
  finalResult: FinalSummarizedResultResponse | null;
}

type QuoteAction =
  | { type: "SET_VEHICLE_NAME"; vehicleName: string }
  | { type: "ADD_PHOTOS"; photos: UploadedPhoto[] }
  | { type: "REMOVE_PHOTO"; id: string }
  | { type: "UPDATE_PHOTO_CATEGORY"; id: string; category: string }
  | { type: "SET_CUSTOMER_COMMENT"; comment: string }
  | { type: "UPDATE_PHOTO_OVERLAY"; id: string; overlay: string }
  | { type: "CLEAR_PHOTOS" }
  | { type: "SET_QUOTE"; result: FinalSummarizedResultResponse }
  | { type: "RESET" };
```

Context Provider는 `App.tsx`의 Router보다 바깥에서 감싸야 합니다.

---

## 6. AI API 연동

`src/services/carVisionApi.ts`에 구현하세요.

**SKR API Base URL**: `http://112.220.206.226:8100` (환경변수 `VITE_API_BASE_URL`) — `/api/v1/skrentalcar/...`, `/health`
**Comment API Base URL**: `http://172.16.10.176:5180` (환경변수 `VITE_COMMENT_API_BASE_URL`) — `/api/v1/extract-structured-comment-claims`, `/api/v1/comment-image-comparison-result`, `/api/v1/claude-vision-check-result`, `/api/v1/final-summarized-result`
**API 인증**: SKR Vision API 요청(`consumeSSE` 내부)에 `access_token` 헤더 포함 (환경변수 `VITE_API_KEY`)
**헬스체크**: `/health` GET은 인증 헤더 없음 (CORS preflight 방지)

SKR 두 엔드포인트는 **SSE(Server-Sent Events)** 스트림을 반환합니다. `consumeSSE<T>()` 헬퍼 함수로 처리:
- `event: progress` → 진행 메시지 콜백
- `event: complete` → 최종 결과 반환
- `event: error` → 에러 발생

Comment API 네 엔드포인트는 일반 JSON POST입니다.

### SSE 헬퍼 함수 구현 (중요)

**주의**: SSE 스트림에서 `event:` 라인과 `data:` 라인이 **서로 다른 청크로 도착**할 수 있습니다. 따라서 `currentEvent` 상태 변수로 이벤트를 추적해야 합니다.

```typescript
// ❌ 잘못된 구현 - nextLine으로 바로 매칭하면 청크 분리 시 실패
if (line.startsWith("event:")) {
  const event = line.slice(6).trim();
  const nextLine = lines[i + 1];  // 다른 청크에 있으면 undefined!
  if (nextLine?.startsWith("data:")) {
    // ...
  }
}

// ✅ 올바른 구현 - currentEvent 변수로 상태 유지
let currentEvent: string | null = null;

for (const line of lines) {
  const trimmedLine = line.trim();

  if (trimmedLine.startsWith("event:")) {
    currentEvent = trimmedLine.slice(6).trim();
    continue;
  }

  if (trimmedLine.startsWith("data:")) {
    const data = trimmedLine.slice(5).trim();

    if (currentEvent === "progress") {
      onProgress?.(data);
    } else if (currentEvent === "complete") {
      result = JSON.parse(data);
    } else if (currentEvent === "error") {
      throw new CarVisionApiError(`SSE error event: ${data}`);
    }

    currentEvent = null;  // 처리 후 리셋
  }
}
```

**핵심 포인트**:
- `currentEvent` 변수로 이전에 받은 event를 기억
- `event:` 라인을 만나면 → `currentEvent`에 저장하고 continue
- `data:` 라인을 만나면 → `currentEvent`를 확인하고 처리
- 처리 완료 후 `currentEvent = null`로 리셋
- 에러 이벤트(`event: error`) 처리 추가
- 디버깅을 위해 받은 이벤트 목록과 남은 버퍼 로깅

### 엔드포인트 1: 앵글 분류 (SSE)

```
POST /api/v1/skrentalcar/exterior-damage/slot-cls
Content-Type: multipart/form-data
Headers: access_token: {API_KEY}
Body: images[] (File 배열), vehicle_category? (선택)
```

응답:
```typescript
interface SkrSlotClsResponse {
  total_images: number;
  front_center: number[];    // 해당 슬롯에 속한 이미지 인덱스 배열
  front_driver: number[];
  front_passenger: number[];
  side_left: number[];
  side_right: number[];
  rear_center: number[];
  rear_driver: number[];
  rear_passenger: number[];
  other: number[];
  non_vehicle: number[];
  request_id: string;        // estimate API에 재사용 (서버 캐시 활용)
}
```

슬롯 → 한국어 매핑 (`CATEGORY_MAP`):
```typescript
// src/services/carVisionApi.ts
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
```

**중요**: API 응답에는 `request_id`, `total_images` 등의 메타 필드도 포함되어 있으므로, **`CATEGORY_MAP`에 정의된 슬롯 키만 처리**해야 합니다.

```typescript
// ❌ 잘못된 방법 - 모든 키 순회 (request_id, total_images도 포함됨)
Object.entries(response).forEach(([slot, indices]) => { ... });

// ✅ 올바른 방법 - CATEGORY_MAP 키만 처리
const slotKeys = Object.keys(CATEGORY_MAP);
slotKeys.forEach((slot) => {
  const indices = response[slot];
  if (Array.isArray(indices) && indices.length > 0) {
    // 한글 카테고리로 변환
    const category = CATEGORY_MAP[slot]; // "정면(중앙)", "비차량" 등
  }
});
```

`classifyCarSlots()` 호출 후 반환된 `request_id`를 `useRef`에 저장 (`slotClsRequestIdRef.current = response.request_id`).

### 엔드포인트 2: 손상 탐지 및 평가 (SSE)

**중요**: `slot-cls`에서 `non_vehicle`으로 분류된 사진(`category === "비차량"`)은 이 API 호출에서 제외합니다.

```
POST /api/v1/skrentalcar/exterior-damage/estimate
Content-Type: multipart/form-data
Headers: access_token: {API_KEY}
Body: images[] (비차량 제외), vehicle_category?, request_id? (slot-cls에서 캐시된 ID), return_detail_visualization=true
```

응답 (`SkrEstimateResponse`):
```typescript
{
  request_id: string;
  meta: {
    damaged_panels: Array<{
      name: string;           // 패널명 (예: "Front-bumper")
      damages: string[];      // 손상 타입 배열 (예: ["Scratched"])
      repair_types: string[]; // 수리 방법 (예: ["BodyRepair", "Repainting"])
    }>;
    geometry_info: {
      geometry_images: Array<{
        image_name: string;   // 원본 파일명 (예: "car_front.jpg")
        vehicle_view_type: string;
        geometry_damage_parts: Array<{ name: string; damages: [...]; box_xywh: [...] }>;
      }>;
    };
    // ...estimated_repair_cost, vehicle_info, etc.
  };
  images: {
    // 손상이 있는 이미지만 포함 (sparse — 입력 이미지 수와 불일치 가능)
    // filename 패턴 (실제 API): "{YYYYMMDD}_{HHmmss}_(warped_)?damage_{원본파일명}"
    // 예: "20260618_120000_damage_car_front.jpg"
    //     "20260618_120001_warped_damage_car_side.jpg"
    vis_damage: Array<{ filename: string; content_type: string; data: string }>; // base64 PNG
  };
}
```

오버레이 이미지 매핑: `vis_damage`는 sparse이고 파일명에 타임스탬프가 붙습니다.
**`/_damage_(.+)$/` 정규식으로 원본 파일명을 추출**해서 매핑하세요.

```typescript
// vis_damage filename = "{timestamp}_(warped_)?damage_{원본파일명}"
// "_damage_" 뒤를 추출하면 원본 파일명과 일치
const visByOriginalName = new Map(
  (skrResult.images.vis_damage ?? []).map((vis) => {
    const m = vis.filename.match(/_damage_(.+)$/);
    return [m ? m[1] : vis.filename, vis.data];
  })
);
skrResult.meta.geometry_info.geometry_images.forEach((geoImg) => {
  const photo = vehiclePhotos.find((p) => p.file?.name === geoImg.image_name);
  if (!photo) return;
  const overlay = visByOriginalName.get(geoImg.image_name);
  if (overlay) {
    dispatch({ type: "UPDATE_PHOTO_OVERLAY", id: photo.id, overlay });
  }
});
```

### 엔드포인트 3: 코멘트 구조화 (조건부)

코멘트가 있을 때만 호출합니다. 결과 `claims[]`를 엔드포인트 4에 전달합니다.

```
POST /api/v1/extract-structured-comment-claims
Content-Type: application/json
Body: {
  estimate_id?: string | null;  // skrResult.request_id
  comment: string;
}
```

응답 (`ExtractStructuredCommentClaimsResponse`):
```typescript
{
  estimate_id: string | null;
  comment: string;
  extractor: string;
  model: string | null;
  llm_error: string | null;
  claims: Array<{
    claim_id: string;
    side: string | null;
    area: string | null;
    panel: string | null;
    damage_type: string | null;
    severity: string | null;
    raw_text: string;
    confidence: number;
  }>;
}
```

코멘트가 없으면 이 단계를 건너뛰고 `claims = []`로 다음 단계를 진행합니다.

### 엔드포인트 4: 코멘트-이미지 비교 (1차 검증)

코멘트 유무와 관계없이 항상 호출합니다 (`claims`는 빈 배열이어도 무관).

```
POST /api/v1/comment-image-comparison-result
Content-Type: application/json
Body: {
  estimate_id?: string | null;
  comment?: string | null;
  claims: StructuredClaim[];     // 엔드포인트 3 결과, 없으면 []
  exterior_damage_estimate: SkrEstimateResponse;
}
```

응답 (`CommentImageComparisonResponse`):
```typescript
{
  estimate_id: string | null;
  comparison_stage: string;
  overall_status: string;
  summary: string;
  claim_results: ComparisonClaimResult[];
  vision_handoff: { required: boolean; reason: string | null; targets: [...] };
}
```

응답 전체를 `claude-vision-check-result`의 `comparison_result`로 전달합니다.

### 엔드포인트 5: AI 검증 (Claude Vision Check)

```
POST /api/v1/claude-vision-check-result
Content-Type: application/json
Body: {
  estimate_id?: string | null;
  comment?: string | null;
  comparison_result: CommentImageComparisonResponse;  // 필수 — 엔드포인트 3 응답 전체
  exterior_damage_estimate: SkrEstimateResponse;      // 필수
  images?: Record<string, string> | null;             // filename → base64
}
```

응답 (`ClaudeVisionCheckResult`):
```typescript
{
  status: string;                  // "completed"
  message?: string;
  data: {
    request_id?: string | null;
    estimate_id?: string | null;
    comment?: string | null;
    meta: {
      vehicle_info?: {
        vehicle_no?: string | null;
        vehicle_name?: string | null;
        vehicle_category?: string | null;
      } | null;
      overall_status?: string | null;    // "all_verified" | "partially_verified" | "needs_human_review"
      headline?: string | null;
      summary?: string | null;
      stats?: Record<string, number> | null;
      decider?: string | null;           // "vision" | "rule_fallback"
      model?: string | null;             // "claude-opus-4-8"
      comment_claims?: Array<{ claim_id: string; raw_text: string }>;
      damaged_panels: Array<{
        name: string;
        damages: string[];
        repair_types: string[];
        requires_review_reasons: string[];
        claude_verdict: {
          agree: boolean;
          confidence: number;             // 0~1
          reasoning: string;
          evidence_images: string[];      // image_name 배열
          comment_corroboration: string | null;  // claim_id 또는 null
          damage_confidences: Record<string, number>;
          damage_verdicts: Array<{
            damage_type: string; agree: boolean; confidence: number; reasoning: string;
          }>;
        };
      }>;
      geometry_info?: {
        geometry_images: Array<{
          image_name: string;
          image_size?: [number, number];
          vehicle_view_type?: string;
          overlay_image_ref?: string | null;
          damage_assessment?: unknown | null;
        }>;
      } | null;
    };
  };
}
```

### 엔드포인트 6: 최종 견적 생성

```
POST /api/v1/final-summarized-result
Content-Type: application/json
Body: {
  vehicle_category: string;
  claude_vision_check_result: ClaudeVisionCheckResult;
  estimate_id?: string | null;
  vehicle_info?: { vehicle_name?: string } | null;
}
```

응답 (`FinalSummarizedResultResponse`):
```typescript
{
  estimate_id: string | null;
  status: string;
  message: string;
  document_info: { document_no: string | null; issue_date: string | null };
  vehicle_info: { vehicle_no: string | null; vehicle_name: string | null; vehicle_category: string | null };
  analysis_result: {
    overall_status: string | null;
    headline: string | null;
    summary: string | null;
    total_damage_count: number;
    estimate_damage_count: number;
    review_damage_count: number;
    image_count: number;
    comment_count: number;
    overall_confidence: number | null;
    model: string | null;
  };
  damage_sections: Array<{
    section_no: number;
    damage_item_id: string;
    panel: string | null;
    panel_label: string | null;          // 한국어 패널명
    damage_types: string[];
    damage_type_labels: string[];        // 한국어 손상 유형
    repair_types: string[];
    repair_type_labels: string[];        // 한국어 수리 방법
    confidence: number | null;
    confidence_percent: number | null;   // 0~100
    reasoning: string | null;
    evidence_images: Array<{ image_name: string }>;
    damage_confidences: Record<string, number>;
    damage_verdicts: ClaudeVisionCheckDamageVerdict[];
    requires_review: boolean;
    requires_review_reasons: string[];
    included_in_estimate: boolean;
  }>;
  estimate_sheet: {
    rows: Array<{
      no: number;
      damage_item_id: string;
      damage_part: string | null;
      repair_content: string;
      quantity: number;
      unit_price: number | null;
      supply_amount: number | null;
      confidence: number | null;
      evidence_images: Array<{ image_name: string }>;
      pricing_status: string;
    }>;
    totals: {
      currency: string;
      supply_amount: number;
      vat_rate: number;
      vat_amount: number;
      total_amount: number;              // VAT 포함 최종 금액
    };
  };
  pending_inputs: string[];
}
```

이 응답이 `dispatch({ type: "SET_QUOTE", result: finalResult })`로 상태에 저장됩니다.

---

## 7. estimateTypeMatch.json 매핑 데이터 활용

### 파일 위치 및 구조

**중요**: API에서 받은 영문 코드를 한국어로 변환하고, UI에 패널 색상을 표시하기 위해 `estimateTypeMatch.json` 파일을 사용합니다.

1. `docs/estimateTypeMatch.json` 파일을 `src/asset/` 폴더로 복사
2. 파일 구조:

```json
{
  "damageTypes": [
    { "code": "Scratched", "name": "스크래치" },
    { "code": "Crushed", "name": "찌그러짐" },
    // ... 16종
  ],
  "panelTypes": [
    { "code": "Front-bumper", "name": "전면 범퍼", "color": "8B55F7" },
    { "code": "Hood", "name": "본넷", "color": "FF9500" },
    // ... 33종 (color는 hex 코드)
  ],
  "repairTypes": [
    { "code": "Polishing", "name": "광택" },
    { "code": "Repainting", "name": "도장" },
    { "code": "BodyRepair", "name": "판금" },
    { "code": "Replacement", "name": "교체" }
  ]
}
```

### carVisionApi.ts에서 매핑 상수 생성

`src/services/carVisionApi.ts`에서 JSON 파일을 import하고 매핑 객체를 생성합니다:

```typescript
import estimateTypeMatch from "@/asset/estimateTypeMatch.json";

// 손상 유형 매핑 (code → name)
export const DAMAGE_TYPE_MAP: Record<string, string> = Object.fromEntries(
  estimateTypeMatch.damageTypes.map((d) => [d.code, d.name])
);

// 패널 매핑 (code → name)
export const PANEL_NAME_MAP: Record<string, string> = Object.fromEntries(
  estimateTypeMatch.panelTypes.map((p) => [p.code, p.name])
);

// 패널 색상 매핑 (code → color hex)
export const PANEL_COLOR_MAP: Record<string, string> = Object.fromEntries(
  estimateTypeMatch.panelTypes.map((p) => [p.code, p.color])
);

// 수리 방법 매핑 (code → name)
export const REPAIR_TYPE_MAP: Record<string, string> = Object.fromEntries(
  estimateTypeMatch.repairTypes.map((r) => [r.code, r.name])
);
```

**주의**: JSON 파일을 import하려면 `tsconfig.app.json`에 다음 설정이 필요합니다:

```json
{
  "compilerOptions": {
    "resolveJsonModule": true
  }
}
```

### Result 페이지에서 패널 색상 활용

QuoteResult.tsx에서 패널별로 색상 배지를 표시할 수 있습니다:

```tsx
import { PANEL_COLOR_MAP } from "@/services/carVisionApi";

// 패널 색상 가져오기
const getPanelColor = (panelCode: string | null) => {
  if (!panelCode) return "#6b7280"; // 기본 회색
  return `#${PANEL_COLOR_MAP[panelCode] || "6b7280"}`;
};

// 사용 예시
<div
  className="w-3 h-3 rounded-full"
  style={{ backgroundColor: getPanelColor(section.panel) }}
/>
<span>{section.panel_label}</span>
```

### API 응답 변환 로직

**중요**: `finalResult`의 `*_labels` 필드는 이미 서버에서 한국어로 변환되어 옵니다. 클라이언트에서 추가 변환이 필요한 경우는 다음과 같습니다:

1. **SKR API 응답 (SkrEstimateResponse)**: 영문 코드만 제공
   ```typescript
   // 예시: damaged_panels[].name = "Front-bumper"
   const koreanName = PANEL_NAME_MAP[panel.name]; // "전면 범퍼"
   ```

2. **Final Result API 응답 (FinalSummarizedResultResponse)**: 이미 한국어 포함
   ```typescript
   // damage_sections[].panel = "Front-bumper" (영문)
   // damage_sections[].panel_label = "전면 범퍼" (한국어, 이미 변환됨)
   // damage_sections[].damage_type_labels = ["스크래치"] (한국어, 이미 변환됨)
   ```

따라서 **Result 페이지에서는 `*_labels` 필드를 직접 사용**하고, 매핑 데이터는 **색상 표시**나 **SKR API 직접 사용 시**에만 활용합니다.

---

## 8. 코드 맵

### `src/services/carVisionApi.ts` 주요 export

```typescript
// 함수
export async function checkHealth(): Promise<HealthResponse>
export async function classifyCarSlots(images, vehicleCategory?): Promise<SkrSlotClsResponse>
export async function estimateExteriorDamage(images, vehicleCategory?, requestId?, onProgress?): Promise<SkrEstimateResponse>
export async function extractStructuredCommentClaims(comment, estimateId?): Promise<ExtractStructuredCommentClaimsResponse>
export async function commentImageComparison(exteriorDamageEstimate, claims, comment?, estimateId?): Promise<CommentImageComparisonResponse>
export async function claudeVisionCheck(request): Promise<ClaudeVisionCheckResult>
export async function finalSummarizedResult(request): Promise<FinalSummarizedResultResponse>

// 매핑 상수 (estimateTypeMatch.json 기반)
export const CATEGORY_MAP: Record<string, string>     // slot 키 → 한국어
export const DAMAGE_TYPE_MAP: Record<string, string>  // code → 한국어 (16종)
export const PANEL_NAME_MAP: Record<string, string>   // code → 한국어 (33종)
export const PANEL_COLOR_MAP: Record<string, string>  // code → hex color (33종)
export const REPAIR_TYPE_MAP: Record<string, string>  // code → 한국어 (4종)

// 에러 클래스
export class CarVisionApiError extends Error
```

---

## 8. 주요 구현 포인트

### 차량 선택 드롭다운 (QuoteRequest.tsx)

```tsx
const VEHICLE_OPTIONS = [
  "경차", "소형", "준중형", "중형", "준대형",
  "특대형", "중형SUV", "대형SUV", "RV/승합", "수입차",
];
```

### 사진 업로드 플로우 (QuoteRequest.tsx)
1. 파일 선택 → `URL.createObjectURL()`로 preview 생성
2. `classifyCarSlots()` 호출 → `/api/v1/skrentalcar/exterior-damage/slot-cls` (SSE) → 앵글 자동 분류
3. 반환된 `request_id`를 `useRef`에 저장
4. **슬롯 매핑**: `CATEGORY_MAP`에 정의된 키만 처리하여 한글로 변환
   ```typescript
   const slotKeys = Object.keys(CATEGORY_MAP) as Array<keyof typeof CATEGORY_MAP>;
   const photosBySlot: Record<string, File[]> = {};

   slotKeys.forEach((slot) => {
     const indices = response[slot];
     if (Array.isArray(indices) && indices.length > 0) {
       photosBySlot[slot] = indices.map((idx) => files[idx]);
     }
   });

   // 한글 카테고리 매핑
   const newPhotos = Object.entries(photosBySlot).flatMap(([slot, slotFiles]) => {
     const category = CATEGORY_MAP[slot]; // "정면(중앙)", "비차량" 등
     return slotFiles.map((file) => ({
       id: crypto.randomUUID(),
       file,
       preview: URL.createObjectURL(file),
       category, // 한글로 변환됨
     }));
   });
   ```
5. API 실패 시 폴백: 순환 할당 (`AUTO_CATEGORIES[index % 8]`)
6. 분류 완료 후 사진 그리드 표시

### 코멘트 입력 (QuoteRequest.tsx)

**중요**: 코멘트는 각 사진마다가 아니라 **전체적으로 하나만** 입력받습니다.

```tsx
{/* 사진 그리드 */}
<div className="grid grid-cols-4 gap-4 mb-6">
  {state.photos.map((photo) => (
    <div key={photo.id} className="relative">
      {/* 사진 이미지 */}
      <div className="aspect-square bg-gray-200 rounded-lg overflow-hidden relative group">
        <img src={photo.preview} alt={photo.category} className="w-full h-full object-cover" />
        <button onClick={() => handleRemovePhoto(photo.id)} className="...">
          <X className="h-4 w-4" />
        </button>
      </div>
      {/* 카테고리 표시만 */}
      <p className="text-sm text-center mt-2 text-gray-700">{photo.category}</p>
    </div>
  ))}
</div>

{/* 전체 코멘트 입력 (사진 그리드 아래에 하나만) */}
<div className="mt-6">
  <label className="block text-sm font-medium text-gray-900 mb-2">
    추가 코멘트 (선택)
  </label>
  <Textarea
    placeholder="손상 부위나 상태에 대한 추가 설명을 입력해주세요..."
    className="w-full min-h-[100px]"
    value={customerComment}
    onChange={(e) => setCustomerComment(e.target.value)}
  />
</div>
```

### UI Spacing 가이드 (QuoteRequest.tsx)

**중요**: 일관된 spacing을 위해 다음 규칙을 따릅니다:

```tsx
<main className="max-w-4xl mx-auto px-6 py-8">
  {/* 섹션 간 간격: mb-8 */}
  <section className="mb-8">
    {/* 섹션 제목과 컨텐츠 간격: mb-3 */}
    <h2 className="text-blue-700 font-medium mb-3">...</h2>
    {/* 컨텐츠 */}
  </section>

  {/* 사진 그리드 */}
  <section className="mb-8">
    <div className="grid grid-cols-4 gap-4 mb-6">
      {/* 각 사진 카드 */}
      <div className="relative">
        {/* 이미지 */}
        <div className="aspect-square ...">...</div>
        {/* 카테고리 (이미지와 간격: mt-2) */}
        <p className="text-sm text-center mt-2">...</p>
      </div>
    </div>

    {/* 코멘트 입력 (그리드와 간격: mt-6) */}
    <div className="mt-6">
      <label className="mb-2">...</label>
      <Textarea className="w-full min-h-[100px]" />
    </div>
  </section>

  {/* 요청하기 버튼 (상단 섹션과 분리되어 있음, mb 없음) */}
  <Button className="w-full h-12">요청하기</Button>
</main>
```

**Spacing 체크리스트**:
- ✅ Header padding: `px-6 py-4`
- ✅ Main content: `max-w-4xl mx-auto px-6 py-8`
- ✅ 섹션 간 간격: `mb-8`
- ✅ 제목과 컨텐츠 간격: `mb-3`
- ✅ 사진 그리드와 코멘트 간격: `mt-6`
- ✅ 버튼 높이: `h-12`

### 분석 요청 파이프라인 (QuoteRequest.tsx `handleRequest`)

5단계 순서로 API를 호출합니다:

```typescript
// Step 1: 손상 탐지 및 평가 — non_vehicle("비차량") 제외
const vehiclePhotos = state.photos.filter((p) => p.file && p.category !== "비차량");
const skrResult = await estimateExteriorDamage(
  vehiclePhotos.map((p) => p.file!),
  vehicleName || undefined,
  slotClsRequestIdRef.current ?? undefined
);

// vis_damage는 sparse + 파일명에 타임스탬프 포함
// "_damage_" 뒤를 추출하면 원본 파일명과 일치 → 인덱스 사용 금지
const visByOriginalName = new Map(
  (skrResult.images.vis_damage ?? []).map((vis) => {
    const m = vis.filename.match(/_damage_(.+)$/);
    return [m ? m[1] : vis.filename, vis.data];
  })
);
skrResult.meta.geometry_info.geometry_images.forEach((geoImg) => {
  const photo = vehiclePhotos.find((p) => p.file?.name === geoImg.image_name);
  if (!photo) return;
  const overlay = visByOriginalName.get(geoImg.image_name);
  if (overlay) dispatch({ type: "UPDATE_PHOTO_OVERLAY", id: photo.id, overlay });
});
setDoneSteps(1);

// Step 2: 코멘트 구조화 (코멘트가 있을 때만)
let claims: StructuredClaim[] = [];
const trimmedComment = customerComment.trim();
if (trimmedComment) {
  const claimsResult = await extractStructuredCommentClaims(trimmedComment, skrResult.request_id);
  claims = claimsResult.claims;
}
setDoneSteps(2);

// Step 3: 코멘트-이미지 비교 (코멘트 유무와 관계없이 항상 호출)
const comparisonResult = await commentImageComparison(
  skrResult, claims, trimmedComment || null, skrResult.request_id
);
setDoneSteps(3);

// Step 4: AI 검증 (Claude Vision Check)
const claudeResult = await claudeVisionCheck({
  estimate_id: skrResult.request_id,
  comment: trimmedComment || null,
  comparison_result: comparisonResult,   // Step 3 응답 전체 전달 (필수)
  exterior_damage_estimate: skrResult,   // 필수
});
setDoneSteps(4);

// Step 5: 최종 견적 생성
const finalResult = await finalSummarizedResult({
  vehicle_category: vehicleName,
  claude_vision_check_result: claudeResult,
  vehicle_info: vehicleName ? { vehicle_name: vehicleName } : undefined,
});
dispatch({ type: "SET_QUOTE", result: finalResult });
setDoneSteps(5);
```

### AI 분석 모달 (QuoteRequest.tsx)
- `Dialog` (shadcn) 사용, `hideClose` prop으로 X 버튼 숨김
- **5단계 진행**: "손상 탐지 및 평가" → "코멘트 구조화" → "코멘트-이미지 비교" → "AI 검증" → "최종 견적 생성"
- `doneSteps` 상태(0~5)로 각 단계의 완료/진행/대기 상태 결정
- 완료(`doneSteps >= 5`) 후 800ms 뒤 `/result`로 이동

### 결과 페이지 데이터 접근 (QuoteResult.tsx)

```typescript
const { finalResult } = state;
if (!finalResult) return <Navigate to="/request" />;

// 근거 사진 조회: 원본 파일명으로 직접 매칭
const photosByName = Object.fromEntries(
  state.photos.filter(p => p.file).map(p => [p.file!.name, p])
);

// evidence_images.image_name은 vis_damage filename일 수 있음
// 패턴: "{date}_{time}_(warped_)?damage_{원본파일명}" → "_damage_" 뒤 추출
function resolvePhoto(evidenceName: string) {
  if (photosByName[evidenceName]) return photosByName[evidenceName];
  const m = evidenceName.match(/_damage_(.+)$/);
  return m ? photosByName[m[1]] : undefined;
}

// 견적 행 조회: damage_item_id로 매칭
const rowByDamageId = Object.fromEntries(
  finalResult.estimate_sheet.rows.map(r => [r.damage_item_id, r])
);

// 총액 (VAT 포함)
const totalAmount = finalResult.estimate_sheet.totals.total_amount;
```

- 아코디언 항목: `finalResult.damage_sections[]`
  - `panel_label`, `damage_type_labels`, `repair_type_labels`, `confidence_percent`, `reasoning`
  - 신뢰도 컬러: `>= 80` → 빨강, `>= 50` → 주황, else → 파랑
- 근거 사진: `section.evidence_images[].image_name` → `resolvePhoto(name)` (vis_damage filename 자동 변환)
- 항목 금액: `rowByDamageId[section.damage_item_id].supply_amount`

### PDF 내보내기 (`src/utils/QuotePdfDocument.tsx`)

`@react-pdf/renderer`로 A4 PDF를 생성합니다. 한국어 렌더링을 위해 **NanumGothic** 폰트를 GitHub raw CDN에서 로드합니다.

데이터 소스:
- `state.finalResult.damage_sections[]` → 손상 항목 목록
- `state.finalResult.estimate_sheet.rows[]` → 견적 행
- `state.finalResult.estimate_sheet.totals` → 합계
- `state.finalResult.document_info.document_no` → 문서 번호
- 근거 사진: `section.evidence_images[].image_name` → `photosByName[name]` (overlay 있으면 overlay, 없으면 preview fallback)

### 견적서 미리보기 모달 (`src/components/QuoteExportModal.tsx`)

데이터 소스는 PDF와 동일:
```typescript
const photosByName = Object.fromEntries(
  state.photos.filter(p => p.file).map(p => [p.file!.name, p])
);
```

탭: `["분석 결과 보고서", "견적서"]`

### useImageZoom 훅 (hooks/useImageZoom.ts)
```typescript
// active: 모달 열림 여부
// 반환: overlayRef, overlayHandlers, imageHandlers, imageStyle, grabbing, didDrag()
```
- body scroll lock (overflow hidden)
- wheel 이벤트: passive:false, scale min 1 / max 8
- 드래그 패닝: hasDraggedRef로 click/drag 충돌 방지

---

## 9. UI 레퍼런스

UI 구현 시 `samples/` 폴더의 이미지를 Read 툴로 읽어 화면을 재현하세요.

| 화면 / 컴포넌트 | 참고 이미지 |
|----------------|-------------|
| 홈 페이지 | `01_home.png` |
| 수리 견적 요청 — 초기 상태 | `02_request_empty.png` |
| 수리 견적 요청 — AI 사진 분류 중 | `04_request_ai-classifying.png` |
| 수리 견적 요청 — 분류 완료 사진 그리드 | `05_request_photos-classified.png` |
| AI 분석 진행 중 모달 | `08_analyzing-modal.png` |
| AI 분석 완료 모달 | `09_analyzing-done-modal.png` |
| AI 견적 결과 페이지 | `10_result_quote.png` |

---

## 10. 스타일 가이드

- **Primary color**: `#1d4ed8` (blue-700) — `index.css`에서 CSS 변수로 정의
- **폰트**: Noto Sans KR (Google Fonts)
- **컴포넌트 테마**: 흰 배경, 회색 보더, 블루 accent
- shadcn `dialog.tsx`에 `hideClose?: boolean` prop 추가 필요

### 브랜딩 (CI 이미지)

- **파일 경로**: `src/asset/Obigo_CI_vertical_for_web(306x500).png`
- **Import**: `import obigoCI from "@/asset/Obigo_CI_vertical_for_web(306x500).png";`
- **홈 페이지**: `<img src={obigoCI} alt="Obigo" className="h-20 object-contain" />`
- **헤더**: `<img src={obigoCI} alt="Obigo" className="h-10 object-contain" />`

---

## 11. 빌드 순서

1. `src/index.css` — Tailwind + 폰트 + CSS 변수
   ```css
   @import 'tailwindcss';
   @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');

   :root {
     --primary: #1d4ed8;
     --primary-hover: #1e40af;
     --text: #1f2937;
     --text-secondary: #6b7280;
     --bg: #ffffff;
     --border: #e5e7eb;
     --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);

     font-family: 'Noto Sans KR', sans-serif;
     -webkit-font-smoothing: antialiased;
     -moz-osx-font-smoothing: grayscale;
   }

   * {
     /* margin: 0; */  /* 주석 처리 - 브라우저 기본 스타일 유지 */
     /* padding: 0; */ /* 주석 처리 - 브라우저 기본 스타일 유지 */
     box-sizing: border-box;
   }

   body {
     margin: 0;
     color: var(--text);
     background: #f9fafb;
   }

   #root {
     min-height: 100vh;
   }

   button {
     font-family: inherit;
   }
   ```
   **중요**: `margin: 0; padding: 0;`는 주석 처리하여 브라우저 기본 스타일을 유지합니다. 각 컴포넌트에서 필요한 spacing만 개별적으로 지정합니다.

2. `src/lib/utils.ts` — cn() 유틸
3. `src/types/api.ts` — API 응답 타입 (SkrSlotClsResponse, SkrEstimateResponse, ClaudeVisionCheckResult, FinalSummarizedResultResponse 등)
4. `src/store/QuoteContext.tsx` — 전역 상태 (finalResult 기반)
5. `src/services/carVisionApi.ts` — API 클라이언트 + 매핑 상수 (estimateTypeMatch.json 기반)
6. `src/hooks/useImageZoom.ts` — 줌 훅
7. `src/components/ui/` — shadcn 컴포넌트 (button, dialog, select, textarea, accordion)
8. `src/pages/Home.tsx`
9. `src/pages/QuoteRequest.tsx`
10. `src/pages/QuoteResult.tsx`
11. `src/components/QuoteExportModal.tsx`
12. `src/utils/QuotePdfDocument.tsx`
13. `src/App.tsx`
14. `src/main.tsx`

---

## 12. 환경 변수

`.env.development`:
```
VITE_API_BASE_URL=http://112.220.206.226:8100
VITE_COMMENT_API_BASE_URL=http://172.16.10.176:5180
VITE_API_KEY=OCbairgnog!97c1b0144da5
```

`carVisionApi.ts`에서:
```typescript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://112.220.206.226:8100";
const COMMENT_API_BASE_URL = import.meta.env.VITE_COMMENT_API_BASE_URL ?? "http://172.16.10.176:5180";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";
```

SKR Vision API 요청(`consumeSSE` 내부)에만 `headers: { access_token: API_KEY }` 포함.
헬스체크(`/health`)는 인증 헤더 없음 (CORS preflight 방지).

---

## 완료 기준

- [ ] 차량 종류 선택 (10종)
- [ ] 사진 업로드 + AI 앵글 분류 (API 실패 시 폴백)
- [ ] **전체 코멘트 입력 (하나만)** — 각 사진마다가 아니라 사진 그리드 아래에 하나의 텍스트 영역
- [ ] 분석 파이프라인 5단계: 손상 탐지 → 코멘트 구조화 → 코멘트-이미지 비교 → AI 검증 → 최종 견적
- [ ] non_vehicle 사진 자동 제외
- [ ] 결과 페이지에서 damage_sections 아코디언
- [ ] 근거 사진 오버레이 표시 + 줌/패닝
- [ ] 견적서 미리보기 모달 (2탭)
- [ ] PDF 저장 (한국어 정상 출력)
- [ ] **UI Spacing 일관성** — 모든 섹션, 제목, 컨텐츠 간 spacing 규칙 준수
