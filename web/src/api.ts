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
    const {data} = await api.get<SettingsResponse>("/api/settings");
    return data;
}

export async function updateSettings(
    body: Record<string, string>
): Promise<{ message: string; settings: UserSettings }> {
    const {data} = await api.put("/api/settings", body);
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
    const {data} = await api.get<OverallSummary>("/api/summary");
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

/* 批量处理 SSE 事件类型 */
export interface BatchProgressEvent {
    index: number;
    total: number;
    filename: string;
    status: "processing";
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
                    if (line.startsWith("event:")) {
                        currentEvent = line.slice(6).trim();
                    } else if (line.startsWith("data:")) {
                        currentData = line.slice(5).trim();
                    } else if (line === "" && currentEvent && currentData) {
                        try {
                            const parsed = JSON.parse(currentData);
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
