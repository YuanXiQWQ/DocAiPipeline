import axios from "axios";

const api = axios.create({ baseURL: "/" });

export interface ClassifyResult {
  doc_type: string;
  confidence: string;
  description: string;
}

export interface ProcessResult {
  doc_type: string;
  filename: string;
  pages: number;
  results: Record<string, unknown>[];
  warnings: string[];
}

export interface FillResult {
  download_url: string;
  filename: string;
  rows_written: number;
}

export async function classifyDocument(file: File): Promise<ClassifyResult> {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await api.post<ClassifyResult>("/api/classify", fd);
  return data;
}

export async function processDocument(
  file: File,
  docType: string = "auto"
): Promise<ProcessResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("doc_type", docType);
  const { data } = await api.post<ProcessResult>("/api/process", fd);
  return data;
}

export async function fillExcel(
  docType: string,
  results: unknown[],
  template?: File
): Promise<FillResult> {
  const fd = new FormData();
  fd.append("doc_type", docType);
  fd.append("results_json", JSON.stringify(results));
  if (template) fd.append("template", template);
  const { data } = await api.post<FillResult>("/api/fill", fd);
  return data;
}

export async function healthCheck(): Promise<{ status: string }> {
  const { data } = await api.get("/health");
  return data;
}

/** 文档类型中文映射 */
export const DOC_TYPE_LABELS: Record<string, string> = {
  auto: "自动识别",
  customs: "进口单据（报关/税款/发票）",
  log_measurement: "原木检尺单",
  log_output: "原木领用出库表",
  soak_pool: "刨切木方入池表",
  slicing: "刨切木方上机表",
  packing: "表板打包报表",
};
