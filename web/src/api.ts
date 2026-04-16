import axios, {AxiosError} from "axios";

const api = axios.create({baseURL: "/"});

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
    const {data} = await api.post<ClassifyResult>("/api/classify", fd);
    return data;
}

export async function processDocument(
    file: File,
    docType: string = "auto"
): Promise<ProcessResult> {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("doc_type", docType);
    const {data} = await api.post<ProcessResult>("/api/process", fd);
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
    const {data} = await api.post<FillResult>("/api/fill", fd);
    return data;
}

export async function healthCheck(): Promise<{ status: string }> {
    const {data} = await api.get("/health");
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
    description_en?: string;
}

export interface UserSettings {
    openai_api_key_masked: string;
    openai_api_key_set: boolean;
    openai_model: string;
    openai_base_url: string;
    language: string;
    default_currency: string;
    default_length_unit: string;
    default_area_unit: string;
    default_volume_unit: string;
    settlement_currency: string;
    settlement_length_unit: string;
    settlement_area_unit: string;
    settlement_volume_unit: string;
}

export interface SettingsResponse {
    settings: UserSettings;
    available_models: ModelInfo[];
}

export async function getSettings(): Promise<SettingsResponse> {
    const {data} = await api.get<SettingsResponse>("/api/settings");
    return data;
}

export async function updateSettings(
    body: Record<string, string>
): Promise<{ message: string; settings: UserSettings }> {
    const {data} = await api.put("/api/settings", body);
    return data;
}

export interface TestKeyResult {
    ok: boolean;
    code: string;
    message: string;
}

export async function testApiKey(apiKey?: string): Promise<TestKeyResult> {
    const {data} = await api.post("/api/settings/test-key", {api_key: apiKey || ""});
    return data;
}

/** 文档类型 → i18n key 映射，使用时需配合 t() 翻译 */
export const DOC_TYPE_KEYS: Record<string, string> = {
    auto: "doc_type.auto",
    customs: "doc_type.customs",
    log_measurement: "doc_type.log_measurement",
    log_output: "doc_type.log_output",
    soak_pool: "doc_type.soak_pool",
    slicing: "doc_type.slicing",
    packing: "doc_type.packing",
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
    const {data} = await api.get<HistoryListResponse>("/api/history", {
        params,
    });
    return data;
}

export async function getHistoryStats(): Promise<HistoryStats> {
    const {data} = await api.get<HistoryStats>("/api/history/stats");
    return data;
}

export async function getHistoryDetail(id: string): Promise<HistoryDetail> {
    const {data} = await api.get<HistoryDetail>(`/api/history/${id}`);
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
    total_amount: number;
    total_volume: number;
    suppliers: Record<string, number>;
}

export interface LogSummaryData {
    total_inbound_logs: number;
    total_inbound_volume: number;
    total_outbound_logs: number;
    total_outbound_volume: number;
    batches: number;
}

export interface FactorySummaryData {
    soak_pool_logs: number;
    soak_pool_volume: number;
    slicing_logs: number;
    slicing_output_area: number;
    packing_pieces: number;
    packing_area: number;
    packing_packages: number;
}

export interface OverallSummary {
    import_summary: ImportSummary;
    log_summary: LogSummaryData;
    factory_summary: FactorySummaryData;
    total_documents_processed: number;
    total_pages_processed: number;
}

export async function getSummary(dateFrom?: string, dateTo?: string): Promise<OverallSummary> {
    const params: Record<string, string> = {};
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    const {data} = await api.get<OverallSummary>("/api/summary", {params});
    return data;
}

// ------------------------------------------------------------------
// 汇总明细行
// ------------------------------------------------------------------

export interface EntryRevision {
    revision_id: string;
    timestamp: string;
    author: string;
    changes: Record<string, { old: unknown; new: unknown }>;
    note: string;
}

export interface SummaryEntry {
    id: string;
    source: string;
    history_id: string;
    filename: string;
    category: string;
    metric: string;
    date: string;
    created_at: string;
    value: number;
    unit: string;
    batch_id: string;
    vehicle_plate: string;
    detail: Record<string, unknown>;
    deleted: boolean;
    deleted_at: string;
    revisions: EntryRevision[];
}

export interface EntryListResponse {
    entries: SummaryEntry[];
    total: number;
}

export async function getSummaryEntries(params: {
    date_from?: string;
    date_to?: string;
    category?: string;
    metric?: string;
    batch_id?: string;
    include_deleted?: boolean;
    only_deleted?: boolean;
    source?: string;
}): Promise<EntryListResponse> {
    const {data} = await api.get<EntryListResponse>("/api/summary/entries", {params});
    return data;
}

export async function createSummaryEntry(req: {
    category: string;
    metric: string;
    date: string;
    value: number;
    unit?: string;
    detail?: Record<string, unknown>;
    note?: string;
}): Promise<SummaryEntry> {
    const {data} = await api.post<SummaryEntry>("/api/summary/entries", req);
    return data;
}

export async function updateSummaryEntry(
    entryId: string,
    updates: Record<string, unknown>,
    note?: string,
): Promise<SummaryEntry> {
    const {data} = await api.put<SummaryEntry>(`/api/summary/entries/${entryId}`, {updates, note});
    return data;
}

export async function deleteSummaryEntry(entryId: string): Promise<SummaryEntry> {
    const {data} = await api.delete<SummaryEntry>(`/api/summary/entries/${entryId}`);
    return data;
}

export async function restoreSummaryEntry(entryId: string): Promise<SummaryEntry> {
    const {data} = await api.post<SummaryEntry>(`/api/summary/entries/${entryId}/restore`);
    return data;
}

export async function getSummaryEntry(entryId: string): Promise<SummaryEntry> {
    const {data} = await api.get<SummaryEntry>(`/api/summary/entries/${entryId}`);
    return data;
}

// ------------------------------------------------------------------
// 实时汇率
// ------------------------------------------------------------------

export interface ExchangeRateResponse {
    base: string;
    rates: Record<string, number>;
    cached: boolean;
}

export async function getExchangeRates(base: string = "EUR"): Promise<ExchangeRateResponse> {
    const {data} = await api.get<ExchangeRateResponse>("/api/summary/exchange-rates", {params: {base}});
    return data;
}

/* 平台检测 */
export interface PlatformInfo {
    desktop: boolean;
    version: string;
}

export async function getPlatform(): Promise<PlatformInfo> {
    const {data} = await api.get<PlatformInfo>("/api/platform");
    return data;
}

/* 开机自启 */
export async function getAutostart(): Promise<{ enabled: boolean }> {
    const {data} = await api.get<{ enabled: boolean }>("/api/autostart");
    return data;
}

export async function setAutostart(enabled: boolean): Promise<{ enabled: boolean }> {
    const {data} = await api.put<{ enabled: boolean }>("/api/autostart", {enabled});
    return data;
}

/* 关闭窗口行为（桌面专属） */
export type CloseBehavior = "minimize_to_tray" | "exit";

export async function getCloseBehavior(): Promise<{ behavior: CloseBehavior }> {
    const {data} = await api.get<{ behavior: CloseBehavior }>("/api/close-behavior");
    return data;
}

export async function setCloseBehavior(behavior: CloseBehavior): Promise<{ behavior: CloseBehavior }> {
    const {data} = await api.put<{ behavior: CloseBehavior }>("/api/close-behavior", {behavior});
    return data;
}

/* 重置窗口大小（桌面专属） */
export async function resetWindow(): Promise<{ message: string }> {
    const {data} = await api.post<{ message: string }>("/api/reset-window");
    return data;
}

/* 版本与更新检查 */
export interface VersionInfo {
    current: string;
    latest?: string;
    has_update: boolean;
    release_url?: string;
}

export async function checkUpdate(): Promise<VersionInfo> {
    const {data} = await api.get<VersionInfo>("/api/version");
    return data;
}

/* 自动更新（桌面专属） */
export async function getAutoUpdate(): Promise<{ enabled: boolean }> {
    const {data} = await api.get<{ enabled: boolean }>("/api/auto-update");
    return data;
}

export async function setAutoUpdate(enabled: boolean): Promise<{ enabled: boolean }> {
    const {data} = await api.put<{ enabled: boolean }>("/api/auto-update", {enabled});
    return data;
}

export interface UpdateStatus {
    status: "idle" | "downloading" | "ready" | "error";
    progress: number;
    message: string;
    version: string;
}

export async function getUpdateStatus(): Promise<UpdateStatus> {
    const {data} = await api.get<UpdateStatus>("/api/update/status");
    return data;
}

export async function triggerUpdateDownload(): Promise<{ message: string }> {
    const {data} = await api.post<{ message: string }>("/api/update/download");
    return data;
}

/* 扫描仪 */
export interface ScannerDevice {
    device_id: string;
    name: string;
}

export interface ScanDevicesResponse {
    available: boolean;
    devices: ScannerDevice[];
}

export interface ScanResultResponse {
    filename: string;
    path: string;
}

export async function getScanDevices(): Promise<ScanDevicesResponse> {
    const {data} = await api.get<ScanDevicesResponse>("/api/scan/devices");
    return data;
}

export async function scanAcquire(deviceId?: string): Promise<ScanResultResponse> {
    const params: Record<string, string> = {};
    if (deviceId) params.device_id = deviceId;
    const {data} = await api.post<ScanResultResponse>("/api/scan/acquire", null, {params});
    return data;
}

/* 批量处理 SSE 事件类型 */
export interface BatchProgressEvent {
    index: number;
    total: number;
    filename: string;
    percent: number;
    stage: string;
}

export interface BatchResultEvent {
    index: number;
    filename: string;
    data: ProcessResult;
}

export interface BatchErrorEvent {
    index: number;
    filename: string;
    error: string;
}

export interface BatchDoneEvent {
    total: number;
    success: number;
    failed: number;
}

/**
 * 批量处理文件，通过 SSE 推送进度。
 * 返回一个 abort 函数用于取消。
 */
export function processBatch(
    files: File[],
    docType: string,
    callbacks: {
        onProgress?: (e: BatchProgressEvent) => void;
        onResult?: (e: BatchResultEvent) => void;
        onError?: (e: BatchErrorEvent) => void;
        onDone?: (e: BatchDoneEvent) => void;
    },
): { abort: () => void } {
    const controller = new AbortController();
    const fd = new FormData();
    for (const f of files) {
        fd.append("files", f);
    }
    fd.append("doc_type", docType);

    (async () => {
        try {
            const response = await fetch("/api/process-batch", {
                method: "POST",
                body: fd,
                headers: {"Accept": "text/event-stream"},
                signal: controller.signal,
            });
            if (!response.ok || !response.body) {
                const text = await response.text();
                callbacks.onError?.({index: 0, filename: "", error: text});
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const {done, value} = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, {stream: true});

                const lines = buffer.split("\n");
                buffer = lines.pop() ?? "";

                let currentEvent = "";
                let currentData = "";
                for (const line of lines) {
                    const trimmed = line.replace(/\r$/, "");
                    if (trimmed.startsWith("event:")) {
                        currentEvent = trimmed.slice(6).trim();
                    } else if (trimmed.startsWith("data:")) {
                        currentData = trimmed.slice(5).trim();
                    } else if (trimmed === "" && currentEvent && currentData) {
                        try {
                            const parsed = JSON.parse(currentData);
                            console.log("[SSE]", currentEvent, parsed);
                            if (currentEvent === "progress") callbacks.onProgress?.(parsed);
                            else if (currentEvent === "result") callbacks.onResult?.(parsed);
                            else if (currentEvent === "error") callbacks.onError?.(parsed);
                            else if (currentEvent === "done") callbacks.onDone?.(parsed);
                        } catch { /* 忽略解析错误 */ }
                        currentEvent = "";
                        currentData = "";
                    }
                }
            }
        } catch (err) {
            if ((err as Error).name !== "AbortError") {
                callbacks.onError?.({index: 0, filename: "", error: String(err)});
            }
        }
    })();

    return {abort: () => controller.abort()};
}
