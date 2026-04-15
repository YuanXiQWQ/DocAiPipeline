import axios, { AxiosError } from "axios";

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

/** 从 axios 错误中提取后端返回的详情信息 */
export function extractErrorMessage(err: unknown): string {
  if (err instanceof AxiosError && err.response?.data) {
    const detail = err.response.data.detail;
    if (typeof detail === "string") return detail;
    if (typeof detail === "object") return JSON.stringify(detail);
  }
  if (err instanceof Error) return err.message;
  return "未知错误";
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  pricing_url: string;
  description: string;
}

export interface UserSettings {
  openai_api_key_masked: string;
  openai_api_key_set: boolean;
  openai_model: string;
  openai_base_url: string;
  language: string;
}

export interface SettingsResponse {
  settings: UserSettings;
  available_models: ModelInfo[];
}

export async function getSettings(): Promise<SettingsResponse> {
  const { data } = await api.get<SettingsResponse>("/api/settings");
  return data;
}

export async function updateSettings(
  body: Record<string, string>
): Promise<{ message: string; settings: UserSettings }> {
  const { data } = await api.put("/api/settings", body);
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

// ------------------------------------------------------------------
// 历史记录
// ------------------------------------------------------------------

export interface HistorySummary {
  id: string;
  timestamp: string;
  doc_type: string;
  filename: string;
  pages: number;
  record_count: number;
  filled: boolean;
  fill_filename: string;
}

export interface HistoryListResponse {
  records: HistorySummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface HistoryStats {
  total_records: number;
  by_doc_type: Record<string, number>;
  total_pages_processed: number;
  total_entries_extracted: number;
  recent_7_days: number;
}

export interface HistoryDetail {
  id: string;
  timestamp: string;
  doc_type: string;
  filename: string;
  pages: number;
  record_count: number;
  warnings: string[];
  results: Record<string, unknown>[];
  filled: boolean;
  fill_filename: string;
}

export async function listHistory(params?: {
  doc_type?: string;
  keyword?: string;
  limit?: number;
  offset?: number;
}): Promise<HistoryListResponse> {
  const { data } = await api.get<HistoryListResponse>("/api/history", {
    params,
  });
  return data;
}

export async function getHistoryStats(): Promise<HistoryStats> {
  const { data } = await api.get<HistoryStats>("/api/history/stats");
  return data;
}

export async function getHistoryDetail(id: string): Promise<HistoryDetail> {
  const { data } = await api.get<HistoryDetail>(`/api/history/${id}`);
  return data;
}

export async function deleteHistory(id: string): Promise<void> {
  await api.delete(`/api/history/${id}`);
}

// ------------------------------------------------------------------
// 数据汇总
// ------------------------------------------------------------------

export interface ImportSummary {
  total_batches: number;
  total_invoices: number;
  total_amount_eur: number;
  total_volume_m3: number;
  suppliers: Record<string, number>;
}

export interface LogSummaryData {
  total_inbound_logs: number;
  total_inbound_m3: number;
  total_outbound_logs: number;
  total_outbound_m3: number;
  batches: number;
}

export interface FactorySummaryData {
  soak_pool_logs: number;
  soak_pool_m3: number;
  slicing_logs: number;
  slicing_output_m2: number;
  packing_pieces: number;
  packing_area_m2: number;
  packing_packages: number;
}

export interface OverallSummary {
  import_summary: ImportSummary;
  log_summary: LogSummaryData;
  factory_summary: FactorySummaryData;
  total_documents_processed: number;
  total_pages_processed: number;
}

export async function getSummary(): Promise<OverallSummary> {
  const { data } = await api.get<OverallSummary>("/api/summary");
  return data;
}
