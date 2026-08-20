/** 工单 T6/T12：后端枚举值的中文短标签与提示文案。 */

export const CLASSIFICATION_ZH: Record<string, string> = {
  trivial: "简单",
  moderate: "中等",
  complex: "复杂",
};

export const CS_SCORE_HINT = "CS 复杂度评分（1–10，越高越复杂）";

export const CONFIDENCE_ZH: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export function classificationZh(raw?: string | null): string | null {
  if (!raw) return null;
  return CLASSIFICATION_ZH[raw] ?? raw;
}
