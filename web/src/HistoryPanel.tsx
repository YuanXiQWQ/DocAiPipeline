import {useState, useEffect, useCallback} from "react";
import {
    Clock,
    FileText,
    Search,
    Trash2,
    ChevronLeft,
    ChevronRight,
    BarChart3,
    CheckCircle,
    Loader2,
} from "lucide-react";
import {
    listHistory,
    getHistoryStats,
    getHistoryDetail,
    deleteHistory,
    extractErrorMessage,
    DOC_TYPE_KEYS,
    type HistorySummary,
    type HistoryStats,
    type HistoryDetail,
} from "./api";
import {useT} from "./i18n";

interface HistoryPanelProps {
    onLoadResult?: (detail: HistoryDetail) => void;
}

export default function HistoryPanel({onLoadResult}: HistoryPanelProps) {
    const t = useT();
    const [records, setRecords] = useState<HistorySummary[]>([]);
    const [total, setTotal] = useState(0);
    const [stats, setStats] = useState<HistoryStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [offset, setOffset] = useState(0);
    const [filterType, setFilterType] = useState<string>("");
    const [keyword, setKeyword] = useState("");
    const [detail, setDetail] = useState<HistoryDetail | null>(null);
    const limit = 20;

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const [listRes, statsRes] = await Promise.all([
                listHistory({
                    doc_type: filterType || undefined,
                    keyword: keyword || undefined,
                    limit,
                    offset,
                }),
                getHistoryStats(),
            ]);
            setRecords(listRes.records);
            setTotal(listRes.total);
            setStats(statsRes);
        } catch (err) {
            console.error("fetch history failed:", extractErrorMessage(err));
        } finally {
            setLoading(false);
        }
    }, [filterType, keyword, offset]);

    useEffect(() => {
        void fetchData();
    }, [fetchData]);

    const handleDelete = async (id: string) => {
        if (!confirm(t("history.delete_confirm"))) return;
        try {
            await deleteHistory(id);
            await fetchData();
        } catch (err) {
            alert(extractErrorMessage(err));
        }
    };

    const handleDetail = async (id: string) => {
        try {
            const d = await getHistoryDetail(id);
            setDetail(d);
        } catch (err) {
            alert(extractErrorMessage(err));
        }
    };

    const formatTime = (iso: string) => {
        try {
            const d = new Date(iso);
            return d.toLocaleString("zh-CN", {
                month: "2-digit",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
            });
        } catch {
            return iso;
        }
    };

    const totalPages = Math.ceil(total / limit);
    const currentPage = Math.floor(offset / limit) + 1;

    // 详情视图
    if (detail) {
        return (
            <div className="space-y-6">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => setDetail(null)}
                            className="p-1.5 rounded-lg hover:bg-gray-100 transition"
                        >
                            <ChevronLeft className="w-5 h-5"/>
                        </button>
                        <div>
                            <h3 className="font-semibold text-gray-900">{detail.filename}</h3>
                            <p className="text-sm text-gray-500">
                                {DOC_TYPE_KEYS[detail.doc_type] ? t(DOC_TYPE_KEYS[detail.doc_type]) : detail.doc_type} · {formatTime(detail.timestamp)}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {onLoadResult && (
                            <button
                                onClick={() => onLoadResult(detail)}
                                className="px-3 py-1.5 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition"
                            >
                                {t("history.load")}
                            </button>
                        )}
                    </div>
                </div>

                <div>
                        {/* 元信息 */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                            <div className="bg-gray-50 rounded-lg p-3">
                                <p className="text-xs text-gray-500">{t("history.detail_pages")}</p>
                                <p className="text-lg font-semibold">{detail.pages}</p>
                            </div>
                            <div className="bg-gray-50 rounded-lg p-3">
                                <p className="text-xs text-gray-500">{t("history.detail_records")}</p>
                                <p className="text-lg font-semibold">{detail.record_count}</p>
                            </div>
                            <div className="bg-gray-50 rounded-lg p-3">
                                <p className="text-xs text-gray-500">{t("history.detail_filled")}</p>
                                <p className="text-lg font-semibold">{detail.filled ? t("history.detail_filled_yes") : t("history.detail_filled_no")}</p>
                            </div>
                            {detail.fill_filename && (
                                <div className="bg-gray-50 rounded-lg p-3">
                                    <p className="text-xs text-gray-500">{t("history.detail_excel")}</p>
                                    <p className="text-sm font-medium truncate">{detail.fill_filename}</p>
                                </div>
                            )}
                        </div>

                        {/* 警告 */}
                        {detail.warnings.length > 0 && (
                            <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                                <p className="text-sm font-medium text-amber-800 mb-1">{t("history.detail_warnings")}</p>
                                {detail.warnings.map((w, i) => (
                                    <p key={i} className="text-sm text-amber-700">{w}</p>
                                ))}
                            </div>
                        )}

                        {/* 识别结果 */}
                        <div>
                            <p className="text-sm font-medium text-gray-700 mb-2">{t("history.detail_results")}</p>
                            <div className="space-y-4">
                                {detail.results.map((rec, ri) => {
                                    const fields = (rec.fields ?? rec.entries ?? []) as Record<string, unknown>[];
                                    /* 字段列表格式：[{field_name, value, ...}] */
                                    const isFieldList = fields.length > 0 && "field_name" in fields[0] && "value" in fields[0];

                                    if (isFieldList) {
                                        return (
                                            <details key={ri} open={detail.results.length <= 3} className="group">
                                                <summary className="text-sm font-medium text-gray-600 cursor-pointer mb-2">
                                                    {t("review.record")} {ri + 1}
                                                </summary>
                                                <div className="border border-gray-200 rounded-lg overflow-hidden">
                                                    <table className="min-w-full text-sm">
                                                        <thead>
                                                        <tr className="bg-gray-50">
                                                            <th className="px-3 py-2 text-left font-medium text-gray-600 border-b border-gray-200 w-1/3">{t("history.field_name")}</th>
                                                            <th className="px-3 py-2 text-left font-medium text-gray-600 border-b border-gray-200">{t("history.field_value")}</th>
                                                        </tr>
                                                        </thead>
                                                        <tbody>
                                                        {fields.map((f, fi) => (
                                                            <tr key={fi} className={fi % 2 === 0 ? "bg-white" : "bg-gray-50/50"}>
                                                                <td className="px-3 py-1.5 border-b border-gray-100 text-gray-500 text-xs">{t(`field.${f.field_name}`) !== `field.${f.field_name}` ? `${t(`field.${f.field_name}`)} (${f.field_name})` : String(f.field_name ?? "")}</td>
                                                                <td className="px-3 py-1.5 border-b border-gray-100 text-gray-900">{String(f.value ?? "—")}</td>
                                                            </tr>
                                                        ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </details>
                                        );
                                    }

                                    /* 表格行格式：[{col1, col2, ...}] */
                                    if (Array.isArray(fields) && fields.length > 0) {
                                        const cols = Object.keys(fields[0]).filter(
                                            k => k !== "needs_review" && k !== "review_reason" && k !== "crop_image_path"
                                        );
                                        return (
                                            <details key={ri} open={detail.results.length <= 3} className="group">
                                                <summary className="text-sm font-medium text-gray-600 cursor-pointer mb-2">
                                                    {t("review.record")} {ri + 1} — {fields.length} {t("review.rows")}
                                                </summary>
                                                <div className="overflow-x-auto border border-gray-200 rounded-lg">
                                                    <table className="min-w-full text-xs border-collapse">
                                                        <thead>
                                                        <tr className="bg-gray-50">
                                                            {cols.map(c => (
                                                                <th key={c} className="px-2 py-1.5 border-b border-gray-200 text-left font-medium text-gray-600 whitespace-nowrap">{t(`field.${c}`) !== `field.${c}` ? `${t(`field.${c}`)} (${c})` : c}</th>
                                                            ))}
                                                        </tr>
                                                        </thead>
                                                        <tbody>
                                                        {fields.slice(0, 50).map((row, rIdx) => (
                                                            <tr key={rIdx} className={rIdx % 2 === 0 ? "bg-white" : "bg-gray-50/50"}>
                                                                {cols.map(c => (
                                                                    <td key={c} className="px-2 py-1 border-b border-gray-100 text-gray-700 whitespace-nowrap">{String(row[c] ?? "")}</td>
                                                                ))}
                                                            </tr>
                                                        ))}
                                                        </tbody>
                                                    </table>
                                                    {fields.length > 50 && (
                                                        <p className="text-xs text-gray-400 px-3 py-1.5">{t("review.more_rows").replace("{n}", String(fields.length - 50))}</p>
                                                    )}
                                                </div>
                                            </details>
                                        );
                                    }

                                    /* 无法识别结构，用简洁 key-value 展示 */
                                    const keys = Object.keys(rec).filter(k => k !== "record_index" && k !== "crop_image_path");
                                    return (
                                        <details key={ri} open={detail.results.length <= 3} className="group">
                                            <summary className="text-sm font-medium text-gray-600 cursor-pointer mb-2">
                                                {t("review.record")} {ri + 1}
                                            </summary>
                                            <div className="border border-gray-200 rounded-lg overflow-hidden">
                                                <table className="min-w-full text-sm">
                                                    <tbody>
                                                    {keys.map((k, ki) => (
                                                        <tr key={ki} className={ki % 2 === 0 ? "bg-white" : "bg-gray-50/50"}>
                                                            <td className="px-3 py-1.5 border-b border-gray-100 text-gray-500 text-xs w-1/3">{t(`field.${k}`) !== `field.${k}` ? `${t(`field.${k}`)} (${k})` : k}</td>
                                                            <td className="px-3 py-1.5 border-b border-gray-100 text-gray-900">{typeof rec[k] === "object" ? JSON.stringify(rec[k]) : String(rec[k] ?? "—")}</td>
                                                        </tr>
                                                    ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </details>
                                    );
                                })}
                            </div>
                        </div>
                </div>
            </div>
        );
    }

    // 主列表视图
    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3 mb-2">
                <Clock className="w-6 h-6 text-primary-600"/>
                <h2 className="text-xl font-semibold text-gray-900">{t("history.title")}</h2>
                {stats && (
                    <span className="text-sm text-gray-500">
                        {t("history.total").replace("{n}", String(stats.total_records))} · {t("history.recent").replace("{n}", String(stats.recent_7_days))}
                    </span>
                )}
            </div>

                {/* 统计卡片 */}
                {stats && stats.total_records > 0 && (
                    <div className="py-3 px-4 bg-gray-50/50 rounded-xl border border-gray-100">
                        <div className="flex gap-6 text-sm">
                            <div className="flex items-center gap-1.5">
                                <BarChart3 className="w-4 h-4 text-primary-500"/>
                                <span className="text-gray-600">{t("history.total_pages")}</span>
                                <span className="font-semibold">{stats.total_pages_processed}</span>
                            </div>
                            <div className="flex items-center gap-1.5">
                                <FileText className="w-4 h-4 text-emerald-500"/>
                                <span className="text-gray-600">{t("history.total_records")}</span>
                                <span className="font-semibold">{stats.total_entries_extracted}</span>
                            </div>
                            {Object.entries(stats.by_doc_type).map(([type, count]) => (
                                <div key={type} className="flex items-center gap-1">
                                    <span
                                        className="text-gray-500">{DOC_TYPE_KEYS[type] ? t(DOC_TYPE_KEYS[type]) : type}</span>
                                    <span className="font-medium text-gray-700">{count}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* 搜索与筛选 */}
                <div className="py-3 flex gap-3">
                    <div className="relative flex-1">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"/>
                        <input
                            type="text"
                            placeholder={t("history.search")}
                            value={keyword}
                            onChange={(e) => {
                                setKeyword(e.target.value);
                                setOffset(0);
                            }}
                            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                        />
                    </div>
                    <select
                        value={filterType}
                        onChange={(e) => {
                            setFilterType(e.target.value);
                            setOffset(0);
                        }}
                        className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-primary-500"
                    >
                        <option value="">{t("history.all_types")}</option>
                        {Object.entries(DOC_TYPE_KEYS)
                            .filter(([k]) => k !== "auto")
                            .map(([k, i18nKey]) => (
                                <option key={k} value={k}>{t(i18nKey)}</option>
                            ))}
                    </select>
                </div>

                {/* 列表 */}
                <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                    {loading ? (
                        <div className="flex items-center justify-center py-20">
                            <Loader2 className="w-6 h-6 animate-spin text-primary-500"/>
                        </div>
                    ) : records.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-20 text-gray-400">
                            <Clock className="w-12 h-12 mb-3"/>
                            <p className="text-lg">{t("history.empty")}</p>
                            <p className="text-sm">{t("history.empty_hint")}</p>
                        </div>
                    ) : (
                        <div className="divide-y divide-gray-100">
                            {records.map((r) => (
                                <div
                                    key={r.id}
                                    className="px-4 py-3 hover:bg-gray-50 transition flex items-center gap-4 cursor-pointer"
                                    onClick={() => handleDetail(r.id)}
                                >
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="font-medium text-gray-900 truncate">{r.filename}</span>
                                            {r.filled && (
                                                <CheckCircle className="w-4 h-4 text-emerald-500 flex-shrink-0"/>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500">
                      <span className="px-1.5 py-0.5 bg-primary-50 text-primary-700 rounded">
                        {DOC_TYPE_KEYS[r.doc_type] ? t(DOC_TYPE_KEYS[r.doc_type]) : r.doc_type}
                      </span>
                                            <span>{r.pages} {t("history.pages_unit")}</span>
                                            <span>{r.record_count} {t("history.records_unit")}</span>
                                            <span>{formatTime(r.timestamp)}</span>
                                        </div>
                                    </div>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            void handleDelete(r.id);
                                        }}
                                        className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500 transition"
                                    >
                                        <Trash2 className="w-4 h-4"/>
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* 分页 */}
                {totalPages > 1 && (
                    <div className="py-3 flex items-center justify-between text-sm">
            <span className="text-gray-500">
              {t("history.page_info").replace("{current}", String(currentPage)).replace("{total}", String(totalPages)).replace("{count}", String(total))}
            </span>
                        <div className="flex gap-2">
                            <button
                                onClick={() => setOffset(Math.max(0, offset - limit))}
                                disabled={offset === 0}
                                className="p-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition"
                            >
                                <ChevronLeft className="w-4 h-4"/>
                            </button>
                            <button
                                onClick={() => setOffset(offset + limit)}
                                disabled={offset + limit >= total}
                                className="p-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition"
                            >
                                <ChevronRight className="w-4 h-4"/>
                            </button>
                        </div>
                    </div>
                )}
        </div>
    );
}
