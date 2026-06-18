import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { FileDown, X, ChevronLeft, ChevronRight } from "lucide-react";
import { useQuoteContext } from "@/store/QuoteContext";
import { pdf } from "@react-pdf/renderer";
import { QuotePdfDocument } from "@/utils/QuotePdfDocument";

interface QuoteExportModalProps {
  onClose: () => void;
}

export default function QuoteExportModal({ onClose }: QuoteExportModalProps) {
  const { state } = useQuoteContext();
  const { finalResult } = state;
  const [activeTab, setActiveTab] = useState<"report" | "estimate">("report");
  const [isGenerating, setIsGenerating] = useState(false);

  if (!finalResult) return null;

  // 사진 맵 생성
  const photosByName = Object.fromEntries(
    state.photos.filter((p) => p.file).map((p) => [p.file!.name, p])
  );

  const resolvePhoto = (evidenceName: string) => {
    if (photosByName[evidenceName]) return photosByName[evidenceName];
    const m = evidenceName.match(/_damage_(.+)$/);
    return m ? photosByName[m[1]] : undefined;
  };

  const getConfidenceColor = (confidence: number | null) => {
    if (confidence === null) return "text-blue-700 bg-blue-100";
    const percent = confidence * 100;
    if (percent >= 80) return "text-red-600 bg-red-100";
    if (percent >= 50) return "text-orange-600 bg-orange-100";
    return "text-blue-700 bg-blue-100";
  };

  const handlePdfDownload = async () => {
    setIsGenerating(true);
    try {
      const doc = <QuotePdfDocument finalResult={finalResult} photosByName={photosByName} />;
      const blob = await pdf(doc).toBlob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `견적서_${finalResult.document_info.document_no || "unknown"}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("PDF 생성 실패:", error);
      alert("PDF 생성에 실패했습니다.");
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] p-0">
        {/* Header */}
        <DialogHeader className="px-6 py-4 border-b border-gray-200 flex-row items-center justify-between">
          <DialogTitle>견적서 미리보기</DialogTitle>
          <Button
            onClick={handlePdfDownload}
            disabled={isGenerating}
            className="gap-2"
            size="sm"
          >
            <FileDown className="h-4 w-4" />
            {isGenerating ? "생성 중..." : "PDF 저장"}
          </Button>
        </DialogHeader>

        {/* Tabs */}
        <div className="flex items-center gap-2 px-6 py-2 border-b border-gray-200">
          <button
            onClick={() => setActiveTab("report")}
            className="text-sm px-1"
          >
            <ChevronLeft className="h-5 w-5 text-gray-400" />
          </button>
          <button
            onClick={() => setActiveTab("report")}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === "report"
                ? "bg-blue-700 text-white"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            분석 결과 보고서
          </button>
          <button
            onClick={() => setActiveTab("estimate")}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === "estimate"
                ? "bg-blue-700 text-white"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            견적서
          </button>
          <button
            onClick={() => setActiveTab("estimate")}
            className="text-sm px-1"
          >
            <ChevronRight className="h-5 w-5 text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto px-6 py-6 bg-gray-50" style={{ maxHeight: "60vh" }}>
          {activeTab === "report" ? (
            <div className="bg-white p-8 rounded-lg shadow-sm">
              <div className="text-right text-xs text-gray-500 mb-4">
                문서 번호: {finalResult.document_info.document_no || "N/A"}
              </div>

              <h1 className="text-2xl font-bold text-center mb-8 border-b-2 border-blue-700 pb-4">
                AI 차량 파손 검수 분석 결과
              </h1>

              <div className="mb-6">
                <p className="text-sm text-gray-700 leading-relaxed mb-4">
                  {finalResult.analysis_result.summary || "요약 정보가 없습니다."}
                </p>
                <div className="text-sm text-gray-600 space-y-1">
                  <p>
                    • 총 손상 개수: {finalResult.analysis_result.total_damage_count}개
                  </p>
                  <p>• 사진 개수: {finalResult.analysis_result.image_count}개</p>
                  <p>
                    • 전체 신뢰도:{" "}
                    {finalResult.analysis_result.overall_confidence
                      ? `${Math.round(finalResult.analysis_result.overall_confidence * 100)}%`
                      : "N/A"}
                  </p>
                </div>
              </div>

              <h2 className="text-lg font-semibold mb-4">손상 항목 상세</h2>
              <div className="space-y-4">
                {finalResult.damage_sections.map((section, index) => {
                  const row = finalResult.estimate_sheet.rows.find(
                    (r) => r.damage_item_id === section.damage_item_id
                  );

                  return (
                    <div
                      key={section.damage_item_id}
                      className="border-l-4 border-blue-700 bg-gray-50 p-4 rounded"
                    >
                      <div className="flex items-start justify-between mb-3">
                        <h3 className="font-semibold text-gray-900">
                          [{index + 1}] {section.panel_label || section.panel}
                        </h3>
                        <span
                          className={`text-xs font-semibold px-2 py-1 rounded ${getConfidenceColor(
                            section.confidence
                          )}`}
                        >
                          신뢰도{" "}
                          {section.confidence_percent !== null
                            ? `${Math.round(section.confidence_percent)}%`
                            : "N/A"}
                        </span>
                      </div>

                      <div className="text-sm text-gray-700 space-y-1 mb-3">
                        <p>손상 유형: {section.damage_type_labels.join(", ")}</p>
                        <p>수리 방법: {section.repair_type_labels.join(", ")}</p>
                        <p>견적 금액: {row?.supply_amount?.toLocaleString() || 0}원</p>
                      </div>

                      {section.reasoning && (
                        <p className="text-sm text-gray-600 border-t pt-3 leading-relaxed">
                          <strong>AI 판단 근거:</strong> {section.reasoning}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>

              <p className="text-xs text-gray-500 text-center mt-8 pt-4 border-t">
                본 견적은 AI 분석 결과에 기반한 것으로, 실제 수리비는 정비소 현장 확인 후 변동될
                수 있습니다.
              </p>
            </div>
          ) : (
            <div className="bg-white p-8 rounded-lg shadow-sm">
              <div className="text-right text-xs text-gray-500 mb-4">
                차량: {finalResult.vehicle_info.vehicle_name || "N/A"}
              </div>

              <h1 className="text-2xl font-bold text-center mb-8 border-b-2 border-blue-700 pb-4">
                수리 견적서
              </h1>

              <table className="w-full text-sm mb-6">
                <thead className="bg-blue-700 text-white">
                  <tr>
                    <th className="py-2 px-3 text-left w-12">No</th>
                    <th className="py-2 px-3 text-left">손상 부위</th>
                    <th className="py-2 px-3 text-left">수리 내용</th>
                    <th className="py-2 px-3 text-right w-28">금액 (원)</th>
                  </tr>
                </thead>
                <tbody>
                  {finalResult.estimate_sheet.rows.map((row, index) => (
                    <tr key={row.damage_item_id} className="border-b border-gray-200">
                      <td className="py-2 px-3">{index + 1}</td>
                      <td className="py-2 px-3">{row.damage_part || "N/A"}</td>
                      <td className="py-2 px-3">{row.repair_content}</td>
                      <td className="py-2 px-3 text-right">
                        {row.supply_amount?.toLocaleString() || 0}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="space-y-2 text-sm">
                <div className="flex justify-end items-center py-2 px-4 bg-gray-100 rounded">
                  <span className="font-medium mr-8">공급가액:</span>
                  <span>{finalResult.estimate_sheet.totals.supply_amount.toLocaleString()}원</span>
                </div>
                <div className="flex justify-end items-center py-2 px-4 bg-gray-100 rounded">
                  <span className="font-medium mr-8">부가세 (VAT):</span>
                  <span>{finalResult.estimate_sheet.totals.vat_amount.toLocaleString()}원</span>
                </div>
                <div className="flex justify-end items-center py-3 px-4 bg-blue-700 text-white rounded">
                  <span className="font-bold text-base mr-8">총 견적 금액:</span>
                  <span className="text-xl font-bold">
                    {finalResult.estimate_sheet.totals.total_amount.toLocaleString()}원
                  </span>
                </div>
              </div>

              <p className="text-xs text-gray-500 text-center mt-8 pt-4 border-t">
                본 견적서는 {finalResult.document_info.issue_date || ""}에 발행되었습니다.
              </p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
