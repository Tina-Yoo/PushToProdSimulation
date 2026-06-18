import { useState, useRef } from "react";
import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Upload, X, Loader2 } from "lucide-react";
import { useQuoteContext } from "@/store/QuoteContext";
import {
  classifyCarSlots,
  estimateExteriorDamage,
  extractStructuredCommentClaims,
  commentImageComparison,
  claudeVisionCheck,
  finalSummarizedResult,
  CATEGORY_MAP,
  CarVisionApiError,
} from "@/services/carVisionApi";
import type { StructuredClaim } from "@/types/api";
import obigoCI from "@/asset/Obigo_CI_vertical_for_web(306x500).png";

const VEHICLE_OPTIONS = [
  "경차",
  "소형",
  "준중형",
  "중형",
  "준대형",
  "특대형",
  "중형SUV",
  "대형SUV",
  "RV/승합",
  "수입차",
];

const AUTO_CATEGORIES = [
  "정면(중앙)",
  "정면(운전석)",
  "정면(동승석)",
  "측면(좌)",
  "측면(우)",
  "후면(중앙)",
  "후면(운전석)",
  "후면(동승석)",
];

export default function QuoteRequest() {
  const { state, dispatch } = useQuoteContext();
  const [, navigate] = useLocation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const slotClsRequestIdRef = useRef<string | null>(null);

  const [vehicleName, setVehicleName] = useState(state.vehicleName);
  const [customerComment, setCustomerComment] = useState(state.customerComment);
  const [isClassifying, setIsClassifying] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [doneSteps, setDoneSteps] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleVehicleChange = (value: string) => {
    setVehicleName(value);
    dispatch({ type: "SET_VEHICLE_NAME", vehicleName: value });
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    setIsClassifying(true);
    setErrorMessage(null);

    try {
      // AI 앵글 분류 호출
      const response = await classifyCarSlots(files, vehicleName || undefined);
      slotClsRequestIdRef.current = response.request_id;

      // CATEGORY_MAP에 정의된 슬롯 키만 처리
      const slotKeys = Object.keys(CATEGORY_MAP) as Array<keyof typeof CATEGORY_MAP>;
      const photosBySlot: Record<string, File[]> = {};

      slotKeys.forEach((slot) => {
        const indices = response[slot as keyof typeof response];
        if (Array.isArray(indices) && indices.length > 0) {
          photosBySlot[slot] = indices.map((idx) => files[idx]);
        }
      });

      // UploadedPhoto 배열 생성 (한글 카테고리 매핑)
      const newPhotos = Object.entries(photosBySlot).flatMap(([slot, slotFiles]) => {
        const category = CATEGORY_MAP[slot]; // 이제 무조건 존재함
        return slotFiles.map((file) => ({
          id: crypto.randomUUID(),
          file,
          preview: URL.createObjectURL(file),
          category,
        }));
      });

      dispatch({ type: "ADD_PHOTOS", photos: newPhotos });
    } catch (error) {
      console.error("Photo classification failed:", error);
      // 폴백: 순환 할당
      const fallbackPhotos = files.map((file, index) => ({
        id: crypto.randomUUID(),
        file,
        preview: URL.createObjectURL(file),
        category: AUTO_CATEGORIES[index % AUTO_CATEGORIES.length],
      }));
      dispatch({ type: "ADD_PHOTOS", photos: fallbackPhotos });
    } finally {
      setIsClassifying(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleRemovePhoto = (id: string) => {
    dispatch({ type: "REMOVE_PHOTO", id });
  };

  const handleRequest = async () => {
    if (state.photos.length === 0) {
      setErrorMessage("사진을 업로드해주세요.");
      return;
    }

    setIsAnalyzing(true);
    setDoneSteps(0);
    setErrorMessage(null);

    try {
      // Step 1: 손상 탐지 및 평가 (non_vehicle 제외)
      const vehiclePhotos = state.photos.filter(
        (p) => p.file && p.category !== "비차량"
      );

      if (vehiclePhotos.length === 0) {
        throw new CarVisionApiError("차량 사진이 없습니다. 비차량 사진만 업로드되었습니다.");
      }

      const skrResult = await estimateExteriorDamage(
        vehiclePhotos.map((p) => p.file!),
        vehicleName || undefined,
        slotClsRequestIdRef.current ?? undefined
      );

      // vis_damage 매핑 (sparse + 타임스탬프 포함)
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

      setDoneSteps(1);

      // Step 2: 코멘트 구조화 (코멘트가 있을 때만)
      let claims: StructuredClaim[] = [];
      const trimmedComment = customerComment.trim();
      if (trimmedComment) {
        const claimsResult = await extractStructuredCommentClaims(
          trimmedComment,
          skrResult.request_id
        );
        claims = claimsResult.claims;
      }
      setDoneSteps(2);

      // Step 3: 코멘트-이미지 비교
      const comparisonResult = await commentImageComparison(
        skrResult,
        claims,
        trimmedComment || null,
        skrResult.request_id
      );
      setDoneSteps(3);

      // Step 4: AI 검증
      const claudeResult = await claudeVisionCheck({
        estimate_id: skrResult.request_id,
        comment: trimmedComment || null,
        comparison_result: comparisonResult,
        exterior_damage_estimate: skrResult,
      });
      setDoneSteps(4);

      // Step 5: 최종 견적 생성
      const finalResult = await finalSummarizedResult({
        vehicle_category: vehicleName,
        claude_vision_check_result: claudeResult,
        vehicle_info: vehicleName ? { vehicle_name: vehicleName } : undefined,
      });
      dispatch({ type: "SET_QUOTE", result: finalResult });
      dispatch({ type: "SET_CUSTOMER_COMMENT", comment: customerComment });
      setDoneSteps(5);

      // 완료 후 결과 페이지로 이동
      setTimeout(() => {
        navigate("/result");
      }, 800);
    } catch (error) {
      console.error("Analysis failed:", error);
      setErrorMessage(
        error instanceof CarVisionApiError
          ? error.message
          : "분석 중 오류가 발생했습니다."
      );
      setIsAnalyzing(false);
      setDoneSteps(0);
    }
  };

  const ANALYSIS_STEPS = [
    "손상 탐지 및 평가",
    "코멘트 구조화",
    "코멘트-이미지 비교",
    "AI 검증",
    "최종 견적 생성",
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <img src={obigoCI} alt="Obigo" className="h-10 object-contain" />
          <h1 className="text-xl font-semibold text-gray-900">수리 견적 요청</h1>
          <div className="w-10"></div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* 차량 선택 */}
        <section className="mb-8">
          <h2 className="text-blue-700 font-medium mb-3">
            견적 산출을 위해 차량을 선택해 주세요
          </h2>
          <Select value={vehicleName} onValueChange={handleVehicleChange}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="차량 선택" />
            </SelectTrigger>
            <SelectContent>
              {VEHICLE_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </section>

        {/* 사진 업로드 */}
        <section className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-blue-700 font-medium">
              견적 산출을 위해 차량 파손 사진을 등록해주세요
            </h2>
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={isClassifying}
              className="gap-2"
            >
              {isClassifying ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  분류 중
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4" />
                  파일 추가
                </>
              )}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={handleFileSelect}
            />
          </div>
          <p className="text-sm text-gray-600 mb-4">
            이미지 파일은 한번에 50장까지 등록 가능합니다.
          </p>

          {state.photos.length === 0 ? (
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-12 text-center bg-white">
              <Upload className="h-12 w-12 mx-auto mb-4 text-gray-400" />
              <p className="text-gray-500">
                첨부할 파일을 여기에 끌어다 놓거나, 파일 추가 버튼을 눌러 파일을 직접 선택해 주세요
              </p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-medium text-gray-900">
                  AI가 자동으로 분류한 사진을 확인해주세요
                </h3>
                <div className="text-sm text-gray-600">
                  <span className="font-medium">파일 {state.photos.length}개</span>
                  {" · "}
                  <button
                    onClick={() => dispatch({ type: "CLEAR_PHOTOS" })}
                    className="text-blue-700 hover:underline"
                  >
                    전체 삭제
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-4 gap-4 mb-6">
                {state.photos.map((photo) => (
                  <div key={photo.id} className="relative">
                    <div className="aspect-square bg-gray-200 rounded-lg overflow-hidden relative group">
                      <img
                        src={photo.preview}
                        alt={photo.category}
                        className="w-full h-full object-cover"
                      />
                      <button
                        onClick={() => handleRemovePhoto(photo.id)}
                        className="absolute top-2 right-2 bg-black/50 hover:bg-black/70 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                    <p className="text-sm text-center mt-2 text-gray-700">
                      {photo.category}
                    </p>
                  </div>
                ))}
              </div>

              {/* 전체 코멘트 입력 */}
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
            </>
          )}
        </section>

        {/* 에러 메시지 */}
        {errorMessage && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-md text-red-700 text-sm">
            {errorMessage}
          </div>
        )}

        {/* 요청하기 버튼 */}
        <Button
          onClick={handleRequest}
          disabled={state.photos.length === 0 || isAnalyzing}
          className="w-full h-12 text-base"
          size="lg"
        >
          {isAnalyzing ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              분석 중...
            </>
          ) : (
            "요청하기"
          )}
        </Button>
      </main>

      {/* AI 분석 진행 모달 */}
      <Dialog open={isAnalyzing} onOpenChange={() => {}}>
        <DialogContent hideClose className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-center">AI 견적 분석</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {ANALYSIS_STEPS.map((step, index) => {
              const stepNumber = index + 1;
              const isDone = doneSteps >= stepNumber;
              const isActive = doneSteps === stepNumber - 1;

              return (
                <div key={step} className="flex items-center gap-3">
                  <div
                    className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center font-medium ${
                      isDone
                        ? "bg-blue-700 text-white"
                        : isActive
                        ? "bg-blue-100 text-blue-700 border-2 border-blue-700"
                        : "bg-gray-200 text-gray-500"
                    }`}
                  >
                    {isDone ? "✓" : stepNumber}
                  </div>
                  <div className="flex-1">
                    <p
                      className={`font-medium ${
                        isDone || isActive ? "text-gray-900" : "text-gray-500"
                      }`}
                    >
                      {step}
                    </p>
                  </div>
                  {isActive && <Loader2 className="h-5 w-5 animate-spin text-blue-700" />}
                </div>
              );
            })}
          </div>
          {doneSteps === 5 && (
            <p className="text-center text-sm text-gray-600">
              분석이 완료되었습니다. 잠시 후 결과 페이지로 이동합니다...
            </p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
