import { useState } from "react";
import { Redirect, Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { FileText, X } from "lucide-react";
import { useQuoteContext } from "@/store/QuoteContext";
import { useImageZoom } from "@/hooks/useImageZoom";
import QuoteExportModal from "@/components/QuoteExportModal";
import obigoCI from "@/asset/Obigo_CI_vertical_for_web(306x500).png";

export default function QuoteResult() {
  const { state } = useQuoteContext();
  const { finalResult } = state;

  const [selectedImage, setSelectedImage] = useState<{
    src: string;
    alt: string;
  } | null>(null);
  const [showExportModal, setShowExportModal] = useState(false);

  const { overlayRef, imageHandlers, imageStyle, didDrag } = useImageZoom(!!selectedImage);

  if (!finalResult) {
    return <Redirect to="/request" />;
  }

  // 사진 맵 생성
  const photosByName = Object.fromEntries(
    state.photos.filter((p) => p.file).map((p) => [p.file!.name, p])
  );

  // vis_damage filename 패턴 변환 함수
  function resolvePhoto(evidenceName: string) {
    if (photosByName[evidenceName]) return photosByName[evidenceName];
    const m = evidenceName.match(/_damage_(.+)$/);
    return m ? photosByName[m[1]] : undefined;
  }

  // 견적 행 맵 생성
  const rowByDamageId = Object.fromEntries(
    finalResult.estimate_sheet.rows.map((r) => [r.damage_item_id, r])
  );

  const totalAmount = finalResult.estimate_sheet.totals.total_amount;

  const handleImageClick = (evidenceName: string, alt: string) => {
    if (didDrag()) return;

    const photo = resolvePhoto(evidenceName);
    if (!photo) return;

    const src = photo.damageOverlay
      ? `data:image/png;base64,${photo.damageOverlay}`
      : photo.preview;

    setSelectedImage({ src, alt });
  };

  const getConfidenceColor = (confidence: number | null) => {
    if (confidence === null) return "text-blue-700";
    const percent = confidence * 100;
    if (percent >= 80) return "text-red-600";
    if (percent >= 50) return "text-orange-600";
    return "text-blue-700";
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <img src={obigoCI} alt="Obigo" className="h-10 object-contain" />
          <h1 className="text-xl font-semibold text-gray-900">AI 견적 안내</h1>
          <Link href="/request">
            <Button variant="outline">새 견적 요청</Button>
          </Link>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="grid grid-cols-[300px_1fr] gap-6">
          {/* Left Sidebar */}
          <aside className="space-y-6">
            {/* 차량 정보 */}
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <h2 className="font-semibold text-gray-900 mb-2">차량 정보</h2>
              <p className="text-sm text-gray-700">
                {finalResult.vehicle_info.vehicle_name || "차량 정보 없음"}
              </p>
            </div>

            {/* AI 검수 요약 */}
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <h2 className="font-semibold text-gray-900 mb-3">AI 검수 요약</h2>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">신뢰도</span>
                  <span
                    className={`font-medium ${getConfidenceColor(
                      finalResult.analysis_result.overall_confidence
                    )}`}
                  >
                    {finalResult.analysis_result.overall_confidence
                      ? `${Math.round(finalResult.analysis_result.overall_confidence * 100)}%`
                      : "N/A"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">총 손상 개수</span>
                  <span className="font-medium text-gray-900">
                    {finalResult.analysis_result.total_damage_count}개
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">사진 개수</span>
                  <span className="font-medium text-gray-900">
                    {finalResult.analysis_result.image_count}개
                  </span>
                </div>
              </div>
              {finalResult.analysis_result.summary && (
                <p className="mt-3 text-sm text-gray-700 border-t pt-3">
                  {finalResult.analysis_result.summary}
                </p>
              )}
            </div>

            {/* 손상 항목 리스트 */}
            <div className="bg-white rounded-lg border border-gray-200">
              <div className="p-4 border-b border-gray-200">
                <h2 className="font-semibold text-gray-900">손상 항목</h2>
              </div>
              <Accordion type="single" collapsible className="px-4">
                {finalResult.damage_sections.map((section) => {
                  const row = rowByDamageId[section.damage_item_id];
                  const supplyAmount = row?.supply_amount ?? 0;

                  return (
                    <AccordionItem key={section.damage_item_id} value={section.damage_item_id}>
                      <AccordionTrigger>
                        <div className="flex flex-col items-start gap-1">
                          <span className="font-medium">
                            {section.panel_label || section.panel}
                          </span>
                          <span className="text-xs text-gray-600">
                            {section.damage_type_labels.join(", ")}
                          </span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent>
                        <div className="space-y-3">
                          {/* 신뢰도 */}
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-gray-600">신뢰도:</span>
                            <span
                              className={`text-sm font-medium ${getConfidenceColor(
                                section.confidence
                              )}`}
                            >
                              {section.confidence_percent !== null
                                ? `${Math.round(section.confidence_percent)}%`
                                : "N/A"}
                            </span>
                          </div>

                          {/* 수리 방법 */}
                          <div>
                            <p className="text-sm text-gray-600 mb-1">수리 방법:</p>
                            <p className="text-sm text-gray-900">
                              {section.repair_type_labels.join(", ")}
                            </p>
                          </div>

                          {/* 견적 금액 */}
                          <div>
                            <p className="text-sm text-gray-600 mb-1">견적 금액:</p>
                            <p className="text-sm font-semibold text-gray-900">
                              {supplyAmount.toLocaleString()}원
                            </p>
                          </div>

                          {/* AI 판단 근거 */}
                          {section.reasoning && (
                            <div>
                              <p className="text-sm text-gray-600 mb-1">AI 판단 근거:</p>
                              <p className="text-sm text-gray-700 leading-relaxed">
                                {section.reasoning}
                              </p>
                            </div>
                          )}

                          {/* 근거 사진 */}
                          {section.evidence_images.length > 0 && (
                            <div>
                              <p className="text-sm text-gray-600 mb-2">근거 사진:</p>
                              <div className="grid grid-cols-2 gap-2">
                                {section.evidence_images.map((ev, idx) => {
                                  const photo = resolvePhoto(ev.image_name);
                                  if (!photo) return null;

                                  const imageSrc = photo.damageOverlay
                                    ? `data:image/png;base64,${photo.damageOverlay}`
                                    : photo.preview;

                                  return (
                                    <button
                                      key={idx}
                                      onClick={() =>
                                        handleImageClick(
                                          ev.image_name,
                                          `${section.panel_label} - 사진 ${idx + 1}`
                                        )
                                      }
                                      className="aspect-square bg-gray-100 rounded overflow-hidden hover:ring-2 hover:ring-blue-700 transition-all"
                                    >
                                      <img
                                        src={imageSrc}
                                        alt={`근거 ${idx + 1}`}
                                        className="w-full h-full object-cover"
                                      />
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  );
                })}
              </Accordion>
            </div>
          </aside>

          {/* Main Content */}
          <main className="space-y-6">
            {/* 견적 총액 */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <div className="flex items-end justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 mb-1">견적 확정</h2>
                  <p className="text-sm text-gray-600">
                    총 {finalResult.damage_sections.length}개 항목
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-600 mb-1">총 견적 금액</p>
                  <p className="text-3xl font-bold text-blue-700">
                    {totalAmount.toLocaleString()}
                    <span className="text-lg">원</span>
                  </p>
                  <p className="text-xs text-gray-500 mt-1">VAT 포함</p>
                </div>
              </div>
            </div>

            {/* 견적서 내보내기 */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <Button
                onClick={() => setShowExportModal(true)}
                className="w-full gap-2"
                size="lg"
              >
                <FileText className="h-5 w-5" />
                견적서 내보내기
              </Button>
            </div>

            {/* 손상 상세 정보 (그리드) */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">손상 상세 정보</h2>
              <div className="space-y-6">
                {finalResult.damage_sections.map((section) => {
                  const row = rowByDamageId[section.damage_item_id];

                  return (
                    <div
                      key={section.damage_item_id}
                      className="border border-gray-200 rounded-lg p-4"
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <h3 className="font-semibold text-gray-900">
                            {section.panel_label || section.panel}
                          </h3>
                          <p className="text-sm text-gray-600 mt-1">
                            {section.damage_type_labels.join(" · ")}
                          </p>
                        </div>
                        <span
                          className={`text-lg font-semibold ${getConfidenceColor(
                            section.confidence
                          )}`}
                        >
                          {section.confidence_percent !== null
                            ? `${Math.round(section.confidence_percent)}%`
                            : "N/A"}
                        </span>
                      </div>

                      {/* 근거 사진 그리드 */}
                      {section.evidence_images.length > 0 && (
                        <div className="grid grid-cols-4 gap-2 mb-3">
                          {section.evidence_images.map((ev, idx) => {
                            const photo = resolvePhoto(ev.image_name);
                            if (!photo) return null;

                            const imageSrc = photo.damageOverlay
                              ? `data:image/png;base64,${photo.damageOverlay}`
                              : photo.preview;

                            return (
                              <button
                                key={idx}
                                onClick={() =>
                                  handleImageClick(
                                    ev.image_name,
                                    `${section.panel_label} - 사진 ${idx + 1}`
                                  )
                                }
                                className="aspect-square bg-gray-100 rounded overflow-hidden hover:ring-2 hover:ring-blue-700 transition-all"
                              >
                                <img
                                  src={imageSrc}
                                  alt={`근거 ${idx + 1}`}
                                  className="w-full h-full object-cover"
                                />
                              </button>
                            );
                          })}
                        </div>
                      )}

                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <span className="text-gray-600">수리 방법: </span>
                          <span className="text-gray-900">
                            {section.repair_type_labels.join(", ")}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-600">견적 금액: </span>
                          <span className="font-semibold text-gray-900">
                            {row?.supply_amount?.toLocaleString() || 0}원
                          </span>
                        </div>
                      </div>

                      {section.reasoning && (
                        <p className="mt-3 text-sm text-gray-700 pt-3 border-t border-gray-200">
                          {section.reasoning}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </main>
        </div>
      </div>

      {/* 이미지 확대 모달 */}
      <Dialog open={!!selectedImage} onOpenChange={() => setSelectedImage(null)}>
        <DialogContent className="max-w-5xl p-0" ref={overlayRef}>
          {selectedImage && (
            <div className="relative">
              <button
                onClick={() => setSelectedImage(null)}
                className="absolute top-4 right-4 z-10 bg-black/50 hover:bg-black/70 text-white rounded-full p-2"
              >
                <X className="h-6 w-6" />
              </button>
              <img
                src={selectedImage.src}
                alt={selectedImage.alt}
                className="w-full max-h-[80vh] object-contain"
                style={imageStyle}
                {...imageHandlers}
              />
              <p className="text-center p-4 bg-gray-900 text-white text-sm">
                {selectedImage.alt}
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* 견적서 내보내기 모달 */}
      {showExportModal && <QuoteExportModal onClose={() => setShowExportModal(false)} />}
    </div>
  );
}
