# Claude Vision Check — 프롬프트 인수인계서

> 대상 저장소: `Tina-Yoo/PushToProd`
> 작성자(재현 대상): **Kaya `<gonea012@naver.com>`** 의 커밋 4건 (2026-06-17)
> 목적: 차량 외판 손상 자동 견적을 **Claude Vision API로 패널 단위 전수 감사(audit)** 하는 엔드포인트를 그대로 재현.

---

## 0. 한눈에 보기 — Kaya가 한 일

| # | 커밋 | 메시지 | 핵심 |
|---|------|--------|------|
| 1 | `c3024f68` | final-summarized-result | `final_summarizer.py`(525줄) 신설 — 패널 단위 Vision 감사 로직 + 프롬프트 최초 작성. 라우터 sync→async, 스키마 확장 |
| 2 | `1f01ebbd` | send damage-overlay images as Vision evidence | 손상 오버레이 이미지를 **증거(EVIDENCE)** 로, 전체 차량 사진을 **FAR VIEW 컨텍스트** 로 메시지에 첨부 |
| 3 | `f0ce7f7f` | Rename final summary API to claude vision check | API를 `claude-vision-check-result` 로 개명 — 라우터/스키마/서비스 파일 3개 신설(594줄), `main.py`·README 갱신 |
| 4 | `fdde18f8` | Map vision evidence to damage overlays | 증거 추적을 `overlay_image_ref` → `image_name` 기준으로 변경, 표시용은 **클로즈업 손상 오버레이 우선** |

> **프롬프트 자체는 커밋 1에서 완성되어 이후 변하지 않았습니다.** 커밋 2~4는 "어떤 이미지를 어떤 라벨로 붙여 보낼지"와 출력 매핑을 다듬은 작업입니다. 즉 **재현의 핵심 = 커밋 1의 프롬프트 + 커밋 2의 이미지 첨부 전략**.

최종 산출물 위치(개명 후):
- 서비스: `server_apis_ test/app/services/claude_vision_check.py`
- 스키마: `server_apis_ test/app/schemas/claude_vision_check.py`
- 라우터: `server_apis_ test/app/routers/claude_vision_check.py` → `POST /api/v1/claude-vision-check-result`

---

## 1. Claude Vision 프롬프트 — 원문 그대로 (★재현 핵심)

### 1-1. System 프롬프트 (`build_system_prompt`)

영어로 작성, **추론(reasoning)만 한국어**로 강제. 패널 어휘를 주입해 "환각으로 다른 패널로 손상을 옮기는 것"을 차단한 것이 설계 포인트.

```text
You audit an automated vehicle exterior-damage estimate. For ONE panel and its
DETECTED DAMAGE TYPES, decide whether each detection is real and located on that
panel, and how confident you are.
- You get EVIDENCE images (close-ups / wide views with damage marked) plus some
FAR VIEW context images. Judge ONLY the named panel.
- The panel name is given and is one of: {PANEL_VOCABULARY} (optionally with
-left/-right). Do not relocate the damage to another panel; judge agreement for THIS panel.
- For EACH damage type return agree (is this damage type really present on this panel?)
and a 0..1 confidence.
- Also return a per-image read: for each EVIDENCE image (by image_name), does it show
this panel's damage, with a 0..1 confidence. Do NOT return entries for FAR VIEW context.
- A receptionist comment may corroborate; treat it as a hint, not proof.
- All reasoning must be concise Korean.
- Return ONLY valid JSON, no markdown:
{"overall_agree": bool, "overall_confidence": number, "overall_reasoning": string,
"damage_type_verdicts": [{"damage_type": string, "agree": bool, "confidence": number, "reasoning": string}],
"per_image": [{"image_name": string, "agree": bool, "confidence": number, "reasoning": string}]}
```

`{PANEL_VOCABULARY}` 에 주입되는 외판 명칭(견적서 표기명):

```python
PANEL_VOCABULARY = [
    "Quarter-panel", "Front-wheel", "Back-window", "Trunk", "Front-door",
    "Rocker-panel", "Grille", "Windshield", "Front-window", "Back-door",
    "Headlight", "Back-wheel", "Back-windshield", "Hood", "Fender",
    "Tail-light", "License-plate", "Front-bumper", "Back-bumper", "Mirror",
    "Roof",
]
```

### 1-2. User 텍스트 (`build_user_text`)

```text
PANEL: {panel_name}
DETECTED DAMAGE TYPES: {damage_types, 쉼표결합}
RECEPTIONIST COMMENT (corroboration hint): {comment_hint}   ← hint 있을 때만 한 줄 추가
TASK: For this panel, judge each damage type (agree + confidence) and give a per-image read.
```

### 1-3. 메시지 content 조립 (`ask_panel_vision`) — 이미지 끼워넣기 방식

이미지마다 **라벨(text 블록)을 먼저** 두고 **그 다음 image 블록**을 두어, 모델이 어떤 이미지가 증거이고 어떤 게 컨텍스트인지 구분하게 함. 마지막에 user 텍스트를 붙임.

```python
content = []
for _iname, label, b64, media_type in images:
    content.append({"type": "text", "text": label})                 # 예: "EVIDENCE image_name=..." / "FAR VIEW (context only) ..."
    content.append({"type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64}})
content.append({"type": "text", "text": build_user_text(panel_name, damage_types, comment_hint)})

payload = {
    "model": CLAUDE_MODEL,            # config.py의 CLAUDE_MODEL
    "max_tokens": 2000,
    "system": build_system_prompt(),  # system은 top-level 파라미터로 전달
    "messages": [{"role": "user", "content": content}],
}
headers = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}
# httpx.AsyncClient(timeout=120) 로 https://api.anthropic.com/v1/messages 에 POST
```

### 1-4. 응답 파싱 & 구조화 출력 계약

- 모델은 **마크다운 없는 순수 JSON** 만 반환하도록 지시됨.
- `extract_text_content()` 로 텍스트 추출 → `extract_json_object()` 로 JSON만 뽑음 → `json.loads` → **Pydantic `PanelVisionVerdict.model_validate`** 로 검증.
- 실패(HTTP/JSON/검증 오류) 시 **예외를 삼키고 `None` 반환** → 룰 기반 폴백(`needs_human_review`)으로 떨어짐.

Pydantic 출력 모델:

```python
class DamageTypeVerdict(BaseModel):   damage_type: str; agree: bool; confidence: float=0.0; reasoning: str=""
class PanelImageVerdict(BaseModel):   image_name: str;  agree: bool; confidence: float=0.0; reasoning: str=""
class PanelVisionVerdict(BaseModel):
    overall_agree: bool; overall_confidence: float=0.0; overall_reasoning: str=""
    damage_type_verdicts: list[DamageTypeVerdict] = []
    per_image: list[PanelImageVerdict] = []
```

### 1-5. 프롬프트에 박혀 있는 설계 원칙 (재현 시 반드시 유지)

1. **단일 패널 격리** — "Judge ONLY the named panel", "Do not relocate the damage". 한 번 호출 = 한 패널.
2. **이중 판정** — (a) 손상유형별 agree+confidence, (b) 이미지별 read. 동시에 요구.
3. **증거/컨텍스트 분리** — EVIDENCE는 판정 대상, FAR VIEW는 컨텍스트일 뿐 `per_image`에 넣지 말 것.
4. **코멘트는 hint, proof 아님** — 접수자 코멘트로 결론을 강제하지 않음.
5. **추론은 한국어, 출력은 JSON-only** — 프롬프트 언어(영어)와 산출 언어(한국어) 분리.
6. **0~1 confidence** + 서버측 `_clamp()` 로 0~1·소수 3자리 보정. `LOW_CONF=0.5` 미만은 저신뢰 플래그.

---

## 2. 패널에 붙일 이미지 고르는 법 (커밋 2의 핵심)

함수 `collect_panel_images()` — 반환 `[(image_name, label, b64, media_type)]`:

- **EVIDENCE(판정 대상)**: 패널의 증거 이미지명마다 `overlay_lookup`(손상 오버레이) 우선, 없으면 원본을 base64로 해석. 라벨 `"EVIDENCE image_name={iname}"`. → 실제 `image_name` 보유 → 모델이 `per_image` 판정.
- **FAR VIEW(컨텍스트)**: `store.wide_refs()` 로 차량 전체 외관 사진을 추가. 라벨 `"FAR VIEW (context only) {filename}"`, **image_name=''** → 모델이 per_image를 돌려주지 않게 함.

상한:
```python
MAX_JUDGED_IMAGES = 8   # 패널당 실제 판정 이미지 수 상한
MAX_WIDE_REFS    = 3    # 패널당 전체-차량 컨텍스트 이미지 수 상한
```

이미지 바이트 해석 우선순위(`ImageStore.resolve`): ① `request.images`(외부 주입 base64) → ② 견적 JSON의 `filename` → ③ 파일명 토큰 매칭. `"<base64:..."` 같은 플레이스홀더는 가짜로 간주(`_is_real_b64`).

---

## 3. 엔드포인트 계약

`POST /api/v1/claude-vision-check-result`

**Request** (`ClaudeVisionCheckResultRequest`):
- `estimate_id: str | None`
- `comment: str | None` — 원본 접수자 자연어 코멘트(보강 hint + 리포트 헤더)
- `comparison_result: CommentImageComparisonResponse` — `/api/v1/comment-image-comparison-result` 출력(어느 패널을 볼지 사전 타게팅)
- `exterior_damage_estimate: dict` — 외판 손상/견적 JSON (geometry parts + `images.*` base64)
- `images: dict[str,str] | None` — 견적 JSON에서 base64가 제거됐을 때 보충용(`image_name/filename → base64`)

**Response** (`ClaudeVisionCheckResultResponse`): `status`, `message`, `data`.
`data`는 견적 결과 구조(`request_id`/`meta`/`geometry_info`)를 미러링하고, 패널마다 `claude_verdict`, 이미지마다 `damage_assessment` 를 덧붙인 형태.

`meta.overall_status`: `all_verified` / `partially_verified` / `needs_human_review`.
`meta.decider`: `vision`(Vision 호출 성공 ≥1) 또는 `rule_fallback`(API 키 없음/전부 실패).

---

## 4. 의존성 — 재현하려면 이 헬퍼들이 먼저 있어야 함

서비스가 `comment_image_comparator.py` 에서 import (대부분 Tina 영역):
- `build_overlay_lookup(estimate)` — image_name → 손상 오버레이 ref
- `extract_geometry_images(estimate)` — geometry 이미지 목록
- `extract_image_identity_tokens(filename)` — 파일명 매칭 토큰
- `extract_text_content(data)` / `extract_json_object(text)` — Claude 응답에서 JSON 추출

설정(`config.py`): `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`. 키 없으면 전부 룰 폴백.

선행 파이프라인: 접수 코멘트 → claim 추출(`comment_claim_extractor.py`) → 이미지 대조(`comment_image_comparator.py`) → **본 Vision 감사**.

---

## 5. 다른 에이전트에게 던질 "재현 프롬프트" (복붙용)

> FastAPI 서비스에 차량 외판 손상 견적을 Claude Vision으로 **패널 단위 감사**하는 엔드포인트 `POST /api/v1/claude-vision-check-result` 를 만들어줘. 요구사항:
> 1. 손상 패널마다 Claude `/v1/messages`(`anthropic-version: 2023-06-01`)를 **개별 호출**한다. 한 호출 = 한 패널.
> 2. System 프롬프트는 §1-1 원문을 그대로 사용 — 외판 어휘(PANEL_VOCABULARY) 주입, "해당 패널만 판정/다른 패널로 손상 이전 금지", 손상유형별 agree+0~1 confidence와 이미지별 read를 **둘 다** 요구, 접수 코멘트는 hint, 추론은 한국어, 출력은 마크다운 없는 순수 JSON.
> 3. 메시지 content는 `[라벨 text → image base64]` 를 이미지마다 반복하고 마지막에 user 텍스트(§1-2). 증거는 `"EVIDENCE image_name=..."`(손상 오버레이 우선, image_name 부여), 전체-차량 사진은 `"FAR VIEW (context only) ..."`(image_name=''). 패널당 판정 8장·컨텍스트 3장 상한.
> 4. 응답은 §1-4 JSON을 추출→Pydantic(`PanelVisionVerdict`)으로 검증. 실패하면 None→룰 폴백(`needs_human_review`).
> 5. `_clamp`(0~1, 소수3자리), `LOW_CONF=0.5` 저신뢰 플래그, 집계(`all_verified`/`partially_verified`/`needs_human_review`)와 한국어 리포트 텍스트 생성.

---

## 부록 — 확인 명령

```bash
# Kaya 커밋만 보기
gh api repos/Tina-Yoo/PushToProd/commits --paginate \
  -q '.[] | select(.commit.author.email=="gonea012@naver.com") | "\(.sha[0:8]) \(.commit.message)"'

# 최종 서비스 파일
gh api "repos/Tina-Yoo/PushToProd/contents/server_apis_%20test/app/services/claude_vision_check.py" \
  -q '.content' | base64 -d
```
