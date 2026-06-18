import { Document, Page, Text, View, StyleSheet, Font, Image } from "@react-pdf/renderer";
import type { FinalSummarizedResultResponse } from "@/types/api";

// NanumGothic 폰트 등록
Font.register({
  family: "NanumGothic",
  fonts: [
    {
      src: "https://cdn.jsdelivr.net/gh/moonspam/NanumSquare@1.0/nanumsquare/NanumSquareR.ttf",
    },
    {
      src: "https://cdn.jsdelivr.net/gh/moonspam/NanumSquare@1.0/nanumsquare/NanumSquareB.ttf",
      fontWeight: "bold",
    },
  ],
});

const styles = StyleSheet.create({
  page: {
    padding: 40,
    fontFamily: "NanumGothic",
    fontSize: 10,
  },
  header: {
    marginBottom: 20,
    borderBottomWidth: 2,
    borderBottomColor: "#1d4ed8",
    paddingBottom: 10,
  },
  title: {
    fontSize: 18,
    fontWeight: "bold",
    textAlign: "center",
    marginBottom: 10,
  },
  docInfo: {
    fontSize: 8,
    textAlign: "right",
    color: "#6b7280",
  },
  section: {
    marginBottom: 15,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: "bold",
    marginBottom: 8,
    color: "#1f2937",
  },
  summaryText: {
    fontSize: 9,
    lineHeight: 1.6,
    color: "#374151",
    marginBottom: 10,
  },
  damageItem: {
    marginBottom: 12,
    padding: 10,
    backgroundColor: "#f9fafb",
    borderRadius: 4,
    borderLeftWidth: 3,
    borderLeftColor: "#1d4ed8",
  },
  damageHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 6,
  },
  damageTitle: {
    fontSize: 11,
    fontWeight: "bold",
    color: "#1f2937",
  },
  confidenceBadge: {
    fontSize: 10,
    fontWeight: "bold",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 3,
  },
  confidenceHigh: {
    backgroundColor: "#fee2e2",
    color: "#dc2626",
  },
  confidenceMedium: {
    backgroundColor: "#fed7aa",
    color: "#ea580c",
  },
  confidenceLow: {
    backgroundColor: "#dbeafe",
    color: "#1d4ed8",
  },
  damageDetail: {
    fontSize: 9,
    color: "#6b7280",
    marginBottom: 3,
  },
  damageReasoning: {
    fontSize: 9,
    color: "#374151",
    marginTop: 6,
    lineHeight: 1.5,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: "#e5e7eb",
  },
  table: {
    marginTop: 15,
  },
  tableHeader: {
    flexDirection: "row",
    backgroundColor: "#1d4ed8",
    padding: 8,
    color: "white",
    fontWeight: "bold",
    fontSize: 9,
  },
  tableRow: {
    flexDirection: "row",
    borderBottomWidth: 1,
    borderBottomColor: "#e5e7eb",
    padding: 8,
    fontSize: 9,
  },
  tableCell: {
    flex: 1,
  },
  tableCellNo: {
    width: 30,
  },
  tableCellAmount: {
    width: 80,
    textAlign: "right",
  },
  totalRow: {
    flexDirection: "row",
    justifyContent: "flex-end",
    padding: 12,
    backgroundColor: "#f3f4f6",
    marginTop: 5,
  },
  totalLabel: {
    fontSize: 11,
    fontWeight: "bold",
    marginRight: 20,
  },
  totalAmount: {
    fontSize: 14,
    fontWeight: "bold",
    color: "#1d4ed8",
  },
  footer: {
    position: "absolute",
    bottom: 30,
    left: 40,
    right: 40,
    textAlign: "center",
    fontSize: 8,
    color: "#9ca3af",
    borderTopWidth: 1,
    borderTopColor: "#e5e7eb",
    paddingTop: 10,
  },
});

interface QuotePdfDocumentProps {
  finalResult: FinalSummarizedResultResponse;
  photosByName: Record<string, { preview: string; damageOverlay?: string }>;
}

export function QuotePdfDocument({ finalResult, photosByName }: QuotePdfDocumentProps) {
  const getConfidenceStyle = (confidence: number | null) => {
    if (confidence === null) return styles.confidenceLow;
    const percent = confidence * 100;
    if (percent >= 80) return styles.confidenceHigh;
    if (percent >= 50) return styles.confidenceMedium;
    return styles.confidenceLow;
  };

  const resolvePhoto = (evidenceName: string) => {
    if (photosByName[evidenceName]) return photosByName[evidenceName];
    const m = evidenceName.match(/_damage_(.+)$/);
    return m ? photosByName[m[1]] : undefined;
  };

  return (
    <Document>
      {/* 분석 결과 보고서 */}
      <Page size="A4" style={styles.page}>
        <View style={styles.header}>
          <Text style={styles.title}>AI 차량 파손 검수 분석 결과</Text>
          <Text style={styles.docInfo}>
            문서 번호: {finalResult.document_info.document_no || "N/A"}
          </Text>
          <Text style={styles.docInfo}>
            발행일: {finalResult.document_info.issue_date || "N/A"}
          </Text>
        </View>

        {/* 요약 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>종합 요약</Text>
          {finalResult.analysis_result.summary && (
            <Text style={styles.summaryText}>{finalResult.analysis_result.summary}</Text>
          )}
          <Text style={styles.summaryText}>
            총 손상 개수: {finalResult.analysis_result.total_damage_count}개 | 사진:{" "}
            {finalResult.analysis_result.image_count}개 | 전체 신뢰도:{" "}
            {finalResult.analysis_result.overall_confidence
              ? `${Math.round(finalResult.analysis_result.overall_confidence * 100)}%`
              : "N/A"}
          </Text>
        </View>

        {/* 손상 항목 상세 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>손상 항목 상세</Text>
          {finalResult.damage_sections.map((section, index) => {
            const row = finalResult.estimate_sheet.rows.find(
              (r) => r.damage_item_id === section.damage_item_id
            );

            return (
              <View key={section.damage_item_id} style={styles.damageItem}>
                <View style={styles.damageHeader}>
                  <Text style={styles.damageTitle}>
                    [{index + 1}] {section.panel_label || section.panel}
                  </Text>
                  <Text
                    style={[styles.confidenceBadge, getConfidenceStyle(section.confidence)]}
                  >
                    신뢰도{" "}
                    {section.confidence_percent !== null
                      ? `${Math.round(section.confidence_percent)}%`
                      : "N/A"}
                  </Text>
                </View>

                <Text style={styles.damageDetail}>
                  손상 유형: {section.damage_type_labels.join(", ")}
                </Text>
                <Text style={styles.damageDetail}>
                  수리 방법: {section.repair_type_labels.join(", ")}
                </Text>
                <Text style={styles.damageDetail}>
                  견적 금액: {row?.supply_amount?.toLocaleString() || 0}원
                </Text>

                {section.reasoning && (
                  <Text style={styles.damageReasoning}>AI 판단 근거: {section.reasoning}</Text>
                )}
              </View>
            );
          })}
        </View>

        <Text style={styles.footer}>
          본 견적은 AI 분석 결과에 기반한 것으로, 실제 수리비는 정비소 현장 확인 후 변동될 수
          있습니다.
        </Text>
      </Page>

      {/* 견적서 */}
      <Page size="A4" style={styles.page}>
        <View style={styles.header}>
          <Text style={styles.title}>수리 견적서</Text>
          <Text style={styles.docInfo}>
            차량: {finalResult.vehicle_info.vehicle_name || "N/A"}
          </Text>
        </View>

        <View style={styles.table}>
          <View style={styles.tableHeader}>
            <Text style={styles.tableCellNo}>No</Text>
            <Text style={[styles.tableCell, { flex: 2 }]}>손상 부위</Text>
            <Text style={styles.tableCell}>수리 내용</Text>
            <Text style={styles.tableCellAmount}>금액 (원)</Text>
          </View>

          {finalResult.estimate_sheet.rows.map((row, index) => (
            <View key={row.damage_item_id} style={styles.tableRow}>
              <Text style={styles.tableCellNo}>{index + 1}</Text>
              <Text style={[styles.tableCell, { flex: 2 }]}>
                {row.damage_part || "N/A"}
              </Text>
              <Text style={styles.tableCell}>{row.repair_content}</Text>
              <Text style={styles.tableCellAmount}>
                {row.supply_amount?.toLocaleString() || 0}
              </Text>
            </View>
          ))}
        </View>

        <View style={styles.totalRow}>
          <Text style={styles.totalLabel}>공급가액:</Text>
          <Text style={{ fontSize: 10, marginRight: 20 }}>
            {finalResult.estimate_sheet.totals.supply_amount.toLocaleString()}원
          </Text>
        </View>
        <View style={styles.totalRow}>
          <Text style={styles.totalLabel}>부가세 (VAT):</Text>
          <Text style={{ fontSize: 10, marginRight: 20 }}>
            {finalResult.estimate_sheet.totals.vat_amount.toLocaleString()}원
          </Text>
        </View>
        <View style={[styles.totalRow, { backgroundColor: "#1d4ed8", marginTop: 0 }]}>
          <Text style={[styles.totalLabel, { color: "white" }]}>총 견적 금액:</Text>
          <Text style={[styles.totalAmount, { color: "white" }]}>
            {finalResult.estimate_sheet.totals.total_amount.toLocaleString()}원
          </Text>
        </View>

        <Text style={styles.footer}>
          본 견적서는 {finalResult.document_info.issue_date || ""}에 발행되었습니다.
        </Text>
      </Page>
    </Document>
  );
}
