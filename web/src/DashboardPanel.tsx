import React, {useState, useEffect, useCallback, useRef, useMemo} from "react";
import {
    BarChart3,
    Truck,
    TreePine,
    Package,
    Scissors,
    ArrowDownCircle,
    ArrowUpCircle,
    Loader2,
    ArrowLeft,
    Pencil,
    Check,
    Plus,
    Minus,
    RotateCcw,
    Clock,
    X,
} from "lucide-react";
import {
    getSummary,
    getSummaryEntries,
    createSummaryEntry,
    updateSummaryEntry,
    deleteSummaryEntry,
    restoreSummaryEntry,
    getExchangeRates,
    getSettings,
    updateSettings,
    listHistory,
    extractErrorMessage,
    type OverallSummary,
    type SummaryEntry,
    type HistorySummary,
} from "./api";
import {useT} from "./i18n";
import {
    type LengthUnit, type AreaUnit, type VolumeUnit, type CurrencyUnit, type UnitConfig,
    LENGTH_UNITS, AREA_UNITS, VOLUME_UNITS, CURRENCY_UNITS, CURRENCY_KEYS,
    LENGTH_TO_M, AREA_TO_M2, VOL_TO_M3,
    DEFAULT_UNITS, unitLabel,
} from "./units";

/* 默认日期范围：今年 */
function thisYearRange(): [string, string] {
    const y = new Date().getFullYear();
    return [`${y}-01-01`, `${y}-12-31`];
}

/* 数值格式化 */
function fmtNum(v: number): string {
    return v.toLocaleString("zh-CN", {maximumFractionDigits: 2});
}

/* ============================================================== */
/* 单位换算系统                                                   */
/* ============================================================== */

/** 单位换算：将原始值从原始单位转换到目标单位（仅视觉展示） */
function convertUnit(value: number, fromUnit: string, units: UnitConfig, rates: Record<string, number>): { value: number; unit: string } {
    if (value == null || isNaN(value)) value = 0;
    const fu = fromUnit.toLowerCase().trim();
    // 货币（通用交叉汇率：value * rateTarget / rateFrom）
    if (CURRENCY_KEYS.has(fu)) {
        if (units.currency === fromUnit.toUpperCase()) return {value, unit: units.currency};
        const fromRate = rates[fu] || 1;
        const toRate = rates[units.currency.toLowerCase()] || 1;
        return {value: value * toRate / fromRate, unit: units.currency};
    }
    // 体积
    if (fu === "m3" || fu === "cm3" || fu === "mm3" || fu === "in3" || fu === "ft3") {
        const fromFactor = VOL_TO_M3[fu as VolumeUnit] ?? 1;
        const toFactor = VOL_TO_M3[units.volume] ?? 1;
        return {value: value * fromFactor / toFactor, unit: unitLabel(units.volume)};
    }
    // 面积
    if (fu === "m2" || fu === "cm2" || fu === "mm2" || fu === "in2" || fu === "ft2") {
        const fromFactor = AREA_TO_M2[fu as AreaUnit] ?? 1;
        const toFactor = AREA_TO_M2[units.area] ?? 1;
        return {value: value * fromFactor / toFactor, unit: unitLabel(units.area)};
    }
    // 长度
    if (fu === "mm" || fu === "cm" || fu === "m" || fu === "in" || fu === "ft") {
        const fromFactor = LENGTH_TO_M[fu as LengthUnit] ?? 1;
        const toFactor = LENGTH_TO_M[units.length] ?? 1;
        return {value: value * fromFactor / toFactor, unit: units.length};
    }
    return {value, unit: fromUnit};
}

/* 统计卡片 */
function StatCard({
    icon, label, value, unit, color, onClick,
}: {
    icon: React.ReactNode;
    label: string;
    value: string | number;
    unit?: string;
    color: string;
    onClick?: () => void;
}) {
    return (
        <div
            className={`rounded-xl border p-4 ${color} ${onClick ? "cursor-pointer hover:shadow-md transition-shadow" : ""}`}
            onClick={onClick}
        >
            <div className="flex items-center gap-2 mb-2">
                {icon}
                <span className="text-sm font-medium text-gray-600">{label}</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">
                {typeof value === "number" ? fmtNum(value) : value}
                {unit && <span className="text-sm font-normal text-gray-500 ml-1">{unit}</span>}
            </p>
        </div>
    );
}

/* ============================================================== */
/* 明细详情页                                                     */
/* ============================================================== */

interface DetailViewProps {
    title: string;
    category: string;
    metric: string;
    dateFrom: string;
    dateTo: string;
    unit: string;
    settlement: UnitConfig;
    display: UnitConfig;
    rates: Record<string, number>;
    onBack: () => void;
}

function DetailView({title, category, metric, dateFrom, dateTo, unit, settlement, display, rates, onBack}: DetailViewProps) {
    const t = useT();
    const [entries, setEntries] = useState<SummaryEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [editing, setEditing] = useState(false);
    const [showDeleted, setShowDeleted] = useState(false);
    const [expandedHistory, setExpandedHistory] = useState<Set<string>>(new Set());
    /* 行内编辑状态 */
    const [editingRow, setEditingRow] = useState<string | null>(null);
    const [editValue, setEditValue] = useState("");
    const [editDate, setEditDate] = useState("");
    const [editNote, setEditNote] = useState("");
    /* 批次号搜索 */
    const [batchSearch, setBatchSearch] = useState("");
    /* 新增行 */
    const [addAfter, setAddAfter] = useState<string | null>(null);
    const [newValue, setNewValue] = useState("");
    const [newDate, setNewDate] = useState("");
    const [newNote, setNewNote] = useState("");
    const [newUnit, setNewUnit] = useState(unit);

    /* 根据单位类型提供可选单位列表 */
    const ul = unit.toLowerCase();
    const isCurrency = CURRENCY_KEYS.has(ul);
    const isVolume = (VOLUME_UNITS as readonly string[]).includes(ul);
    const isArea = (AREA_UNITS as readonly string[]).includes(ul);
    const isLength = (LENGTH_UNITS as readonly string[]).includes(ul);
    const unitOptions: string[] = isCurrency ? [...CURRENCY_UNITS]
        : isVolume ? [...VOLUME_UNITS]
        : isArea ? [...AREA_UNITS]
        : isLength ? [...LENGTH_UNITS]
        : [unit];

    const fetchEntries = useCallback(() => {
        setLoading(true);
        getSummaryEntries({
            date_from: dateFrom, date_to: dateTo,
            category, metric,
            batch_id: batchSearch || undefined,
            include_deleted: showDeleted,
        })
            .then(r => setEntries(r.entries))
            .finally(() => setLoading(false));
    }, [dateFrom, dateTo, category, metric, batchSearch, showDeleted]);

    useEffect(() => { fetchEntries(); }, [fetchEntries]);

    const active = entries.filter(e => !e.deleted);
    // 确定当前页面对应的结算 key（如 "m3"）用于第二步换算
    const settledKey = CURRENCY_KEYS.has(ul) ? settlement.currency
        : (VOLUME_UNITS as readonly string[]).includes(ul) ? settlement.volume
        : (AREA_UNITS as readonly string[]).includes(ul) ? settlement.area
        : (LENGTH_UNITS as readonly string[]).includes(ul) ? settlement.length
        : unit;
    const settledTotal = active.reduce((s, e) => s + convertUnit(e.value, e.unit || unit, settlement, rates).value, 0);
    const settledUnit = convertUnit(0, unit, settlement, rates).unit;
    const displayTotal = active.reduce((s, e) => {
        const settled = convertUnit(e.value, e.unit || unit, settlement, rates);
        return s + convertUnit(settled.value, settledKey, display, rates).value;
    }, 0);
    const displayUnitLabel = convertUnit(0, settledKey, display, rates).unit;
    const showBoth = (() => {
        if (CURRENCY_KEYS.has(ul)) return settlement.currency !== display.currency;
        if ((VOLUME_UNITS as readonly string[]).includes(ul)) return settlement.volume !== display.volume;
        if ((AREA_UNITS as readonly string[]).includes(ul)) return settlement.area !== display.area;
        if ((LENGTH_UNITS as readonly string[]).includes(ul)) return settlement.length !== display.length;
        return false;
    })();

    const handleSaveEdit = async (id: string) => {
        const v = parseFloat(editValue);
        if (isNaN(v)) return;
        const updates: Record<string, unknown> = {value: v};
        if (editDate) updates.date = editDate;
        await updateSummaryEntry(id, updates, editNote || undefined);
        setEditingRow(null);
        fetchEntries();
    };

    const handleDelete = async (id: string) => {
        await deleteSummaryEntry(id);
        fetchEntries();
    };

    const handleRestore = async (id: string) => {
        await restoreSummaryEntry(id);
        fetchEntries();
    };

    const handleAddRow = async () => {
        const v = parseFloat(newValue);
        if (isNaN(v)) return;
        await createSummaryEntry({
            category, metric,
            date: newDate || new Date().toISOString().slice(0, 10),
            value: v, unit: newUnit,
            note: newNote || undefined,
        });
        setAddAfter(null);
        setNewValue("");
        setNewDate("");
        setNewNote("");
        fetchEntries();
    };

    const toggleHistory = (id: string) => {
        setExpandedHistory(prev => prev.has(id) ? new Set() : new Set([id]));
    };

    return (
        <div className="space-y-4">
            {/* 顶栏 */}
            <div className="flex items-center justify-between">
                <button onClick={onBack} className="flex items-center gap-1 text-sm text-primary-600 hover:underline">
                    <ArrowLeft className="w-4 h-4"/> {t("dashboard.back")}
                </button>
                <div className="flex items-center gap-2">
                    <input type="text" placeholder={t("dashboard.search_batch")} value={batchSearch}
                           onChange={e => setBatchSearch(e.target.value)}
                           className="border border-gray-200 rounded-lg px-2 py-1 text-sm w-40"/>
                    <label className="flex items-center gap-1.5 text-xs text-gray-500">
                        <input type="checkbox" checked={showDeleted} onChange={e => setShowDeleted(e.target.checked)} className="rounded"/>
                        {t("dashboard.show_deleted")}
                    </label>
                    <button
                        onClick={() => setEditing(!editing)}
                        className={`flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border transition ${
                            editing ? "bg-emerald-50 border-emerald-300 text-emerald-700" : "bg-white border-gray-200 text-gray-600 hover:bg-gray-50"
                        }`}
                    >
                        {editing ? <><Check className="w-3.5 h-3.5"/> {t("dashboard.done_editing")}</>
                            : <><Pencil className="w-3.5 h-3.5"/> {t("dashboard.edit_mode")}</>}
                    </button>
                </div>
            </div>

            {/* 标题 + 总计 */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h3 className="text-lg font-semibold text-gray-900 mb-1">{title}</h3>
                <p className="text-sm text-gray-500 mb-4">{dateFrom} ~ {dateTo}</p>
                {showBoth ? (
                    <div className="space-y-1">
                        <p className="text-3xl font-bold text-gray-900">{fmtNum(settledTotal)} <span className="text-base font-normal text-gray-500">{settledUnit}</span></p>
                        <p className="text-xl text-gray-500">≈ {fmtNum(displayTotal)} <span className="text-sm">{displayUnitLabel}</span></p>
                    </div>
                ) : (
                    <p className="text-3xl font-bold text-gray-900">{fmtNum(settledTotal)} <span className="text-base font-normal text-gray-500">{settledUnit}</span></p>
                )}
            </div>

            {/* 明细表格 */}
            {loading ? (
                <div className="flex justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-primary-500"/></div>
            ) : entries.length === 0 && !editing ? (
                <p className="text-center text-gray-400 py-10">{t("dashboard.no_entries")}</p>
            ) : entries.length === 0 && editing ? (
                <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                    {addAfter === "__empty__" ? (
                        <div className="flex items-center gap-2 px-4 py-3 bg-emerald-50">
                            <input type="date" value={newDate} onChange={e => setNewDate(e.target.value)} className="border rounded px-2 py-1 text-xs w-36"/>
                            <span className="text-xs text-amber-600">{t("dashboard.manual_entry")}</span>
                            <input type="number" step="any" placeholder={t("dashboard.entry_value")} value={newValue} onChange={e => setNewValue(e.target.value)}
                                   className="border rounded px-2 py-1 text-xs w-28 text-right"/>
                            {unitOptions.length > 1 && (
                                <select value={newUnit} onChange={e => setNewUnit(e.target.value)} className="border rounded px-1 py-1 text-xs">
                                    {unitOptions.map(u => <option key={u} value={u}>{unitLabel(u)}</option>)}
                                </select>
                            )}
                            <input type="text" placeholder={t("dashboard.entry_note")} value={newNote} onChange={e => setNewNote(e.target.value)}
                                   className="border rounded px-2 py-1 text-xs w-24"/>
                            <button onClick={handleAddRow} className="p-1 text-emerald-600 hover:text-emerald-800"><Check className="w-4 h-4"/></button>
                            <button onClick={() => setAddAfter(null)} className="p-1 text-gray-400 hover:text-red-500"><X className="w-4 h-4"/></button>
                        </div>
                    ) : (
                        <button
                            onClick={() => setAddAfter("__empty__")}
                            className="flex items-center justify-center gap-2 w-full px-4 py-4 text-sm text-gray-400 hover:text-emerald-600 hover:bg-emerald-50 transition"
                        >
                            <Plus className="w-4 h-4"/> {t("dashboard.add_row")}
                        </button>
                    )}
                </div>
            ) : (
                <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                    <table className="min-w-full text-sm">
                        <thead>
                        <tr className="bg-gray-50 text-gray-600">
                            <th className="px-4 py-2.5 text-left font-medium">{t("dashboard.entry_date")}</th>
                            <th className="px-4 py-2.5 text-left font-medium">{t("dashboard.batch_id")}</th>
                            <th className="px-4 py-2.5 text-left font-medium">{t("dashboard.source_file")}</th>
                            <th className="px-4 py-2.5 text-right font-medium">{t("dashboard.entry_value")}</th>
                            <th className="px-4 py-2.5 text-center font-medium w-32"></th>
                        </tr>
                        </thead>
                        <tbody>
                        {entries.map((entry) => (
                            <React.Fragment key={entry.id}>
                                <tr className={`border-t border-gray-100 ${entry.deleted ? "bg-gray-50 opacity-50" : ""} ${editingRow === entry.id ? "bg-primary-50" : ""}`}>
                                    <td className="px-4 py-2.5">
                                        {editingRow === entry.id ? (
                                            <input type="date" value={editDate} onChange={e => setEditDate(e.target.value)} className="border rounded px-2 py-1 text-xs w-36"/>
                                        ) : (
                                            <div>
                                                <span className="text-gray-700">{entry.date}</span>
                                                <span className="text-gray-400 text-xs ml-1">{entry.created_at.slice(11, 19)}</span>
                                            </div>
                                        )}
                                    </td>
                                    <td className="px-4 py-2.5 text-gray-600">
                                        {entry.batch_id && <span className="font-mono text-xs">{entry.batch_id}</span>}
                                        {entry.vehicle_plate && <span className="ml-1.5 px-1 py-0.5 rounded text-xs bg-slate-100 text-slate-500">{entry.vehicle_plate}</span>}
                                    </td>
                                    <td className="px-4 py-2.5 text-gray-600 truncate max-w-[200px]">
                                        <span className={`inline-block px-1.5 py-0.5 rounded text-xs mr-1.5 ${
                                            entry.source === "manual" ? "bg-amber-100 text-amber-700" : "bg-primary-100 text-primary-700"
                                        }`}>{entry.source === "manual" ? t("dashboard.manual_entry") : t("dashboard.auto_entry")}</span>
                                        {entry.filename || "—"}
                                    </td>
                                    <td className="px-4 py-2.5 text-right font-mono">
                                        {editingRow === entry.id ? (
                                            <input type="number" step="any" value={editValue} onChange={e => setEditValue(e.target.value)} className="border rounded px-2 py-1 text-xs w-28 text-right"/>
                                        ) : (
                                            <span className={entry.deleted ? "line-through" : ""}>{fmtNum(entry.value)} {unitLabel(entry.unit || unit)}</span>
                                        )}
                                    </td>
                                    <td className="px-4 py-2.5 text-center">
                                        <div className="flex items-center justify-center gap-1">
                                            {/* 编辑历史标记 */}
                                            {entry.revisions.length > 0 && (
                                                <button onClick={() => toggleHistory(entry.id)} className="p-1 text-gray-400 hover:text-primary-500" title={t("dashboard.history")}>
                                                    <Clock className="w-3.5 h-3.5"/>
                                                </button>
                                            )}
                                            {editing && !entry.deleted && editingRow !== entry.id && (
                                                <>
                                                    <button onClick={() => { setEditingRow(entry.id); setEditValue(String(entry.value)); setEditDate(entry.date); setEditNote(""); }}
                                                            className="p-1 text-gray-400 hover:text-primary-500" title={t("dashboard.edit_mode")}>
                                                        <Pencil className="w-3.5 h-3.5"/>
                                                    </button>
                                                    <button onClick={() => setAddAfter(entry.id)} className="p-1 text-gray-400 hover:text-emerald-500" title={t("dashboard.add_row")}>
                                                        <Plus className="w-3.5 h-3.5"/>
                                                    </button>
                                                    <button onClick={() => handleDelete(entry.id)} className="p-1 text-gray-400 hover:text-red-500" title={t("dashboard.delete_row")}>
                                                        <Minus className="w-3.5 h-3.5"/>
                                                    </button>
                                                </>
                                            )}
                                            {editing && entry.deleted && (
                                                <button onClick={() => handleRestore(entry.id)} className="p-1 text-gray-400 hover:text-emerald-500" title={t("dashboard.restore_row")}>
                                                    <RotateCcw className="w-3.5 h-3.5"/>
                                                </button>
                                            )}
                                            {editingRow === entry.id && (
                                                <>
                                                    <input type="text" placeholder={t("dashboard.entry_note")} value={editNote} onChange={e => setEditNote(e.target.value)}
                                                           className="border rounded px-2 py-1 text-xs w-24 mx-1"/>
                                                    <button onClick={() => handleSaveEdit(entry.id)} className="p-1 text-emerald-600 hover:text-emerald-800"><Check className="w-4 h-4"/></button>
                                                    <button onClick={() => setEditingRow(null)} className="p-1 text-gray-400 hover:text-red-500"><X className="w-4 h-4"/></button>
                                                </>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                                {/* 修订历史展开 */}
                                {expandedHistory.has(entry.id) && entry.revisions.length > 0 && (
                                    <tr>
                                        <td colSpan={5} className="bg-slate-50 px-6 py-3">
                                            <p className="text-xs font-medium text-gray-500 mb-2">{t("dashboard.history")}</p>
                                            <div className="space-y-1.5">
                                                {entry.revisions.map((rev) => (
                                                    <div key={rev.revision_id} className="text-xs text-gray-500 flex gap-3">
                                                        <span className="text-gray-400 whitespace-nowrap">{rev.timestamp.slice(0, 16).replace("T", " ")}</span>
                                                        <span className={`px-1.5 py-0.5 rounded ${rev.author === "user" ? "bg-amber-50 text-amber-600" : "bg-primary-50 text-primary-600"}`}>{rev.author}</span>
                                                        <span className="text-gray-600">
                                                            {Object.entries(rev.changes).map(([k, v]) => (
                                                                <span key={k} className="mr-2">{k}: <span className="line-through text-red-400">{String(v.old)}</span> → <span className="text-emerald-600">{String(v.new)}</span></span>
                                                            ))}
                                                        </span>
                                                        {rev.note && <span className="italic text-gray-400">{rev.note}</span>}
                                                    </div>
                                                ))}
                                            </div>
                                        </td>
                                    </tr>
                                )}
                                {/* 新增行表单 */}
                                {addAfter === entry.id && (
                                    <tr className="bg-emerald-50 border-t border-emerald-200">
                                        <td className="px-4 py-2.5">
                                            <input type="date" value={newDate} onChange={e => setNewDate(e.target.value)} className="border rounded px-2 py-1 text-xs w-36"/>
                                        </td>
                                        <td className="px-4 py-2.5"></td>
                                        <td className="px-4 py-2.5 text-xs text-amber-600">{t("dashboard.manual_entry")}</td>
                                        <td className="px-4 py-2.5">
                                            <div className="flex items-center gap-1 justify-end">
                                                <input type="number" step="any" placeholder={t("dashboard.entry_value")} value={newValue} onChange={e => setNewValue(e.target.value)}
                                                       className="border rounded px-2 py-1 text-xs w-28 text-right"/>
                                                {unitOptions.length > 1 && (
                                                    <select value={newUnit} onChange={e => setNewUnit(e.target.value)} className="border rounded px-1 py-1 text-xs">
                                                        {unitOptions.map(u => <option key={u} value={u}>{unitLabel(u)}</option>)}
                                                    </select>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-4 py-2.5 text-center">
                                            <div className="flex items-center justify-center gap-1">
                                                <input type="text" placeholder={t("dashboard.entry_note")} value={newNote} onChange={e => setNewNote(e.target.value)}
                                                       className="border rounded px-2 py-1 text-xs w-24"/>
                                                <button onClick={handleAddRow} className="p-1 text-emerald-600 hover:text-emerald-800"><Check className="w-4 h-4"/></button>
                                                <button onClick={() => setAddAfter(null)} className="p-1 text-gray-400 hover:text-red-500"><X className="w-4 h-4"/></button>
                                            </div>
                                        </td>
                                    </tr>
                                )}
                            </React.Fragment>
                        ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

/* ============================================================== */
/* 处理记录列表（只读）                                            */
/* ============================================================== */

const DOC_TYPES = ["customs", "log_measurement", "log_output", "soak_pool", "slicing", "packing"];

function HistoryListView({title, docType, onBack}: {
    title: string;
    docType?: string;
    onBack: () => void;
}) {
    const t = useT();
    const [records, setRecords] = useState<HistorySummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [filterType, setFilterType] = useState(docType ?? "");

    const fetchRecords = useCallback(() => {
        setLoading(true);
        listHistory({doc_type: filterType || undefined, limit: 500})
            .then(r => setRecords(r.records))
            .finally(() => setLoading(false));
    }, [filterType]);

    useEffect(() => { fetchRecords(); }, [fetchRecords]);

    const totalPages = records.reduce((s, r) => s + r.pages, 0);

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <button onClick={onBack} className="flex items-center gap-1 text-sm text-primary-600 hover:underline">
                    <ArrowLeft className="w-4 h-4"/> {t("dashboard.back")}
                </button>
                <div className="flex items-center gap-2">
                    <select value={filterType} onChange={e => setFilterType(e.target.value)}
                            className="border border-gray-200 rounded-lg px-2 py-1 text-sm">
                        <option value="">{t("dashboard.all_types")}</option>
                        {DOC_TYPES.map(dt => <option key={dt} value={dt}>{t(`doc_type.${dt}`)}</option>)}
                    </select>
                </div>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h3 className="text-lg font-semibold text-gray-900 mb-1">{title}</h3>
                <p className="text-sm text-gray-500">{records.length} {t("dashboard.unit_doc")} · {totalPages} {t("dashboard.unit_page")}</p>
            </div>

            {loading ? (
                <div className="flex justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-primary-500"/></div>
            ) : records.length === 0 ? (
                <p className="text-center text-gray-400 py-10">{t("dashboard.no_entries")}</p>
            ) : (
                <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                    <table className="min-w-full text-sm">
                        <thead>
                        <tr className="bg-gray-50 text-gray-600">
                            <th className="px-4 py-2.5 text-left font-medium">{t("dashboard.col_date")}</th>
                            <th className="px-4 py-2.5 text-left font-medium">{t("dashboard.col_filename")}</th>
                            <th className="px-4 py-2.5 text-left font-medium">{t("dashboard.col_doctype")}</th>
                            <th className="px-4 py-2.5 text-right font-medium">{t("dashboard.col_pages")}</th>
                            <th className="px-4 py-2.5 text-right font-medium">{t("dashboard.col_records")}</th>
                        </tr>
                        </thead>
                        <tbody>
                        {records.map(r => (
                            <tr key={r.id} className="border-t border-gray-100 hover:bg-gray-50">
                                <td className="px-4 py-2.5 text-gray-700">{r.timestamp.slice(0, 10)} <span className="text-gray-400 text-xs">{r.timestamp.slice(11, 19)}</span></td>
                                <td className="px-4 py-2.5 text-gray-600 truncate max-w-[250px]">{r.filename}</td>
                                <td className="px-4 py-2.5">
                                    <span className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600">{t(`doc_type.${r.doc_type}`)}</span>
                                </td>
                                <td className="px-4 py-2.5 text-right font-mono">{r.pages}</td>
                                <td className="px-4 py-2.5 text-right font-mono">{r.record_count}</td>
                            </tr>
                        ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

/* ============================================================== */
/* 筛选面板（展开式）                                              */
/* ============================================================== */

function UnitRow({label, units, setUnits, rates, ratesLive, baseCurrency, showRateHint}: {
    label: string;
    units: UnitConfig; setUnits: (u: UnitConfig) => void;
    rates: Record<string, number>; ratesLive: boolean;
    baseCurrency?: CurrencyUnit;
    showRateHint?: boolean;
}) {
    const t = useT();
    return (
        <div className="flex flex-wrap items-center gap-4">
            <span className="text-xs font-medium text-gray-500 w-16 shrink-0">{label}</span>
            {/* 货币 */}
            <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-400">{t("dashboard.currency")}</span>
                <select value={units.currency}
                        onChange={e => setUnits({...units, currency: e.target.value as CurrencyUnit})}
                        className="border border-gray-200 rounded-lg px-2 py-1 text-sm">
                    {CURRENCY_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                </select>
                {showRateHint && ratesLive && baseCurrency && units.currency !== baseCurrency && (() => {
                    const fromRate = rates[baseCurrency.toLowerCase()] || 1;
                    const toRate = rates[units.currency.toLowerCase()] || 1;
                    const crossRate = toRate / fromRate;
                    return <span className="text-xs text-gray-400">1 {baseCurrency} = {crossRate.toFixed(2)} {units.currency}</span>;
                })()}
            </div>
            <div className="h-4 border-l border-gray-200"/>
            {/* 长度 */}
            <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-400">{t("dashboard.length")}</span>
                <select value={units.length}
                        onChange={e => setUnits({...units, length: e.target.value as LengthUnit})}
                        className="border border-gray-200 rounded-lg px-2 py-1 text-sm">
                    {LENGTH_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                </select>
            </div>
            {/* 面积 */}
            <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-400">{t("dashboard.area")}</span>
                <select value={units.area}
                        onChange={e => setUnits({...units, area: e.target.value as AreaUnit})}
                        className="border border-gray-200 rounded-lg px-2 py-1 text-sm">
                    {AREA_UNITS.map(u => <option key={u} value={u}>{unitLabel(u)}</option>)}
                </select>
            </div>
            {/* 体积 */}
            <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-400">{t("dashboard.volume")}</span>
                <select value={units.volume}
                        onChange={e => setUnits({...units, volume: e.target.value as VolumeUnit})}
                        className="border border-gray-200 rounded-lg px-2 py-1 text-sm">
                    {VOLUME_UNITS.map(u => <option key={u} value={u}>{unitLabel(u)}</option>)}
                </select>
            </div>
        </div>
    );
}

function FilterPanel({
    dateFrom, dateTo, setDateFrom, setDateTo,
    settlement, setSettlement,
    display, setDisplay,
    rates, ratesLive,
    onReset,
}: {
    dateFrom: string; dateTo: string;
    setDateFrom: (v: string) => void; setDateTo: (v: string) => void;
    settlement: UnitConfig; setSettlement: (u: UnitConfig) => void;
    display: UnitConfig; setDisplay: (u: UnitConfig) => void;
    rates: Record<string, number>; ratesLive: boolean;
    onReset: () => void;
}) {
    const t = useT();
    const [defFrom, defTo] = thisYearRange();
    return (
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            {/* 日期范围 */}
            <div className="flex flex-wrap items-end gap-4">
                <div>
                    <label className="block text-xs text-gray-500 mb-1">{t("dashboard.date_from")}</label>
                    <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                           className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"/>
                </div>
                <div>
                    <label className="block text-xs text-gray-500 mb-1">{t("dashboard.date_to")}</label>
                    <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                           className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"/>
                </div>
                <button onClick={() => { setDateFrom(defFrom); setDateTo(defTo); }}
                        className="px-3 py-1.5 border border-gray-200 text-gray-500 text-sm rounded-lg hover:bg-gray-50 transition">
                    {t("dashboard.reset_filter")}
                </button>
            </div>

            <div className="border-t border-gray-100"/>

            {/* 结算单位（持久化，与设置页同步） */}
            <div className="space-y-2">
                <UnitRow label={t("dashboard.settlement_units")} units={settlement} setUnits={setSettlement}
                         rates={rates} ratesLive={ratesLive}/>
            </div>

            <div className="border-t border-gray-100"/>

            {/* 换算展示单位（临时切换） */}
            <div className="space-y-2">
                <UnitRow label={t("dashboard.display_units")} units={display} setUnits={setDisplay}
                         rates={rates} ratesLive={ratesLive}
                         baseCurrency={settlement.currency} showRateHint/>
                <div className="flex justify-end">
                    <button onClick={onReset}
                            className="px-2.5 py-1 text-xs border border-gray-200 text-gray-500 rounded-lg hover:bg-gray-50 transition">
                        {t("dashboard.reset_filter")}
                    </button>
                </div>
            </div>
        </div>
    );
}

/* ============================================================== */
/* 主看板                                                         */
/* ============================================================== */

export default function DashboardPanel() {
    const t = useT();
    const [data, setData] = useState<OverallSummary | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [defFrom, defTo] = thisYearRange();
    const [dateFrom, setDateFrom] = useState(defFrom);
    const [dateTo, setDateTo] = useState(defTo);

    /* 结算单位（持久化，修改后回写设置） */
    const [settlement, setSettlementRaw] = useState<UnitConfig>({...DEFAULT_UNITS});
    const settlementLoaded = useRef(false);

    const setSettlement = useCallback((u: UnitConfig) => {
        setSettlementRaw(u);
        if (settlementLoaded.current) {
            updateSettings({
                settlement_currency: u.currency,
                settlement_length_unit: u.length,
                settlement_area_unit: u.area,
                settlement_volume_unit: u.volume,
            }).catch(() => {});
        }
    }, []);

    /* 换算展示单位（临时，不回写设置） */
    const [display, setDisplay] = useState<UnitConfig>({...DEFAULT_UNITS});
    const [rates, setRates] = useState<Record<string, number>>({});
    const [ratesLive, setRatesLive] = useState(false);

    useEffect(() => {
        getSettings().then(res => {
            const s = res.settings;
            const cfg: UnitConfig = {
                currency: (s.settlement_currency || DEFAULT_UNITS.currency) as CurrencyUnit,
                length: (s.settlement_length_unit || DEFAULT_UNITS.length) as LengthUnit,
                area: (s.settlement_area_unit || DEFAULT_UNITS.area) as AreaUnit,
                volume: (s.settlement_volume_unit || DEFAULT_UNITS.volume) as VolumeUnit,
            };
            setSettlementRaw(cfg);
            setDisplay(cfg);
            settlementLoaded.current = true;
        }).catch(() => { settlementLoaded.current = true; });
    }, []);


    /* 所有明细条目（用于前端逐条换算求和） */
    const [entries, setEntries] = useState<SummaryEntry[]>([]);

    /* 明细视图状态 */
    const [detailView, setDetailView] = useState<{title: string; category: string; metric: string; unit: string} | null>(null);
    /* 历史记录列表视图状态 */
    const [historyView, setHistoryView] = useState<{title: string; docType?: string} | null>(null);

    const fetchData = useCallback(() => {
        setLoading(true);
        setError(null);
        Promise.all([
            getSummary(dateFrom, dateTo),
            getSummaryEntries({date_from: dateFrom, date_to: dateTo}),
        ])
            .then(([summaryData, entryData]) => {
                setData(summaryData);
                setEntries(entryData.entries);
            })
            .catch(err => setError(extractErrorMessage(err)))
            .finally(() => setLoading(false));
    }, [dateFrom, dateTo]);

    /** 后台刷新汇总数据，不触发 loading 状态 */
    const silentRefresh = useCallback(() => {
        Promise.all([
            getSummary(dateFrom, dateTo),
            getSummaryEntries({date_from: dateFrom, date_to: dateTo}),
        ])
            .then(([summaryData, entryData]) => {
                setData(summaryData);
                setEntries(entryData.entries);
            })
            .catch(() => {});
    }, [dateFrom, dateTo]);

    const fetchRates = useCallback(() => {
        getExchangeRates("EUR")
            .then(r => { setRates(r.rates); setRatesLive(true); })
            .catch(() => setRatesLive(false));
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);
    useEffect(() => { fetchRates(); }, [fetchRates]);

    /** 两步换算：原始单位 → 结算单位 → 展示单位 */
    const cv = useCallback((value: number, fromUnit: string) => {
        const settled = convertUnit(value, fromUnit, settlement, rates);
        // 第二步用 settlement 的原始 key（如 "m3"）而非 label（如 "m³"）
        const fu = fromUnit.toLowerCase().trim();
        const settledKey = CURRENCY_KEYS.has(fu) ? settlement.currency
            : (VOLUME_UNITS as readonly string[]).includes(fu) ? settlement.volume
            : (AREA_UNITS as readonly string[]).includes(fu) ? settlement.area
            : (LENGTH_UNITS as readonly string[]).includes(fu) ? settlement.length
            : settled.unit;
        return convertUnit(settled.value, settledKey, display, rates);
    }, [settlement, display, rates]);

    /** 从 entries 逐条换算求和（正确处理混合单位） */
    const agg = useMemo(() => {
        const r = {
            importAmount: 0, importVolume: 0,
            inboundVolume: 0, outboundVolume: 0,
            soakVolume: 0, slicingArea: 0, packingArea: 0,
        };
        for (const e of entries) {
            if (e.deleted) continue;
            const unit = e.unit || "";
            const val = e.value ?? 0;
            if (e.category === "import") {
                r.importAmount += cv(val, unit).value;
                r.importVolume += cv(parseFloat(String(e.detail?.volume_m3 ?? 0)), "m3").value;
            } else if (e.category === "log_inbound") {
                r.inboundVolume += cv(val, unit).value;
            } else if (e.category === "log_outbound") {
                r.outboundVolume += cv(val, unit).value;
            } else if (e.category === "soak_pool") {
                r.soakVolume += cv(parseFloat(String(e.detail?.volume_m3 ?? 0)), "m3").value;
            } else if (e.category === "slicing") {
                r.slicingArea += cv(parseFloat(String(e.detail?.output_m2 ?? 0)), "m2").value;
            } else if (e.category === "packing") {
                r.packingArea += cv(parseFloat(String(e.detail?.area_m2 ?? 0)), "m2").value;
            }
        }
        return r;
    }, [entries, cv]);

    const scrollRef = useRef(0);

    const openDetail = (title: string, category: string, metric: string, unit: string) => {
        scrollRef.current = window.scrollY;
        setDetailView({title, category, metric, unit});
        requestAnimationFrame(() => window.scrollTo(0, 0));
    };

    const openHistory = (title: string, docType?: string) => {
        scrollRef.current = window.scrollY;
        setHistoryView({title, docType});
        requestAnimationFrame(() => window.scrollTo(0, 0));
    };

    const handleBackToMain = (cb: () => void) => {
        cb();
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                window.scrollTo(0, scrollRef.current);
            });
        });
    };

    const resetAll = () => {
        setDateFrom(defFrom);
        setDateTo(defTo);
        setDisplay({...settlement});
    };

    const isSubView = !!(historyView || detailView);

    return (
        <>
        {/* 历史记录列表视图 */}
        {historyView && (
            <div className="space-y-6">
                <div className="flex items-center gap-3 mb-2">
                    <BarChart3 className="w-6 h-6 text-primary-600"/>
                    <h2 className="text-xl font-semibold text-gray-900">{t("dashboard.history_list_title")}</h2>
                </div>
                <HistoryListView
                    title={historyView.title}
                    docType={historyView.docType}
                    onBack={() => handleBackToMain(() => setHistoryView(null))}
                />
            </div>
        )}

        {/* 明细视图 */}
        {detailView && (
            <div className="space-y-6">
                <div className="flex items-center gap-3 mb-2">
                    <BarChart3 className="w-6 h-6 text-primary-600"/>
                    <h2 className="text-xl font-semibold text-gray-900">{t("dashboard.detail_title")}</h2>
                </div>
                <DetailView
                    title={detailView.title}
                    category={detailView.category}
                    metric={detailView.metric}
                    dateFrom={dateFrom}
                    dateTo={dateTo}
                    unit={detailView.unit}
                    settlement={settlement}
                    display={display}
                    rates={rates}
                    onBack={() => handleBackToMain(() => { setDetailView(null); silentRefresh(); })}
                />
            </div>
        )}

        {/* 主看板视图：子视图打开时隐藏但不卸载 */}
        <div style={{display: isSubView ? "none" : undefined}} className="space-y-8">
            <div className="flex items-center gap-3">
                <BarChart3 className="w-6 h-6 text-primary-600"/>
                <h2 className="text-xl font-semibold text-gray-900">{t("dashboard.title")}</h2>
            </div>

            {/* 展开式筛选面板 */}
            <FilterPanel
                dateFrom={dateFrom} dateTo={dateTo}
                setDateFrom={setDateFrom} setDateTo={setDateTo}
                settlement={settlement} setSettlement={setSettlement}
                display={display} setDisplay={setDisplay}
                rates={rates} ratesLive={ratesLive}
                onReset={resetAll}
            />

            {loading ? (
                <div className="flex items-center justify-center py-20">
                    <Loader2 className="w-6 h-6 animate-spin text-primary-500"/>
                </div>
            ) : error ? (
                <div className="text-center py-20 text-red-500">{error}</div>
            ) : data ? (
                <div className="space-y-8">
                    {/* 总览 */}
                    <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">{t("dashboard.overview")}</h3>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <StatCard icon={<BarChart3 className="w-5 h-5 text-primary-500"/>} label={t("dashboard.docs_processed")} value={data.total_documents_processed} unit={t("dashboard.unit_doc")} color="bg-primary-50 border-primary-200"
                                      onClick={() => openHistory(t("dashboard.docs_processed"))}/>
                            <StatCard icon={<BarChart3 className="w-5 h-5 text-indigo-500"/>} label={t("dashboard.pages_processed")} value={data.total_pages_processed} unit={t("dashboard.unit_page")} color="bg-indigo-50 border-indigo-200"
                                      onClick={() => openHistory(t("dashboard.pages_processed"))}/>
                            <StatCard icon={<ArrowDownCircle className="w-5 h-5 text-emerald-500"/>} label={t("dashboard.log_inbound")} value={agg.inboundVolume} unit={unitLabel(display.volume)} color="bg-emerald-50 border-emerald-200"
                                      onClick={() => openDetail(t("dashboard.inbound_volume"), "log_inbound", "inbound_batch", "m3")}/>
                            <StatCard icon={<ArrowUpCircle className="w-5 h-5 text-amber-500"/>} label={t("dashboard.log_outbound")} value={agg.outboundVolume} unit={unitLabel(display.volume)} color="bg-amber-50 border-amber-200"
                                      onClick={() => openDetail(t("dashboard.outbound_volume"), "log_outbound", "outbound_batch", "m3")}/>
                        </div>
                    </div>

                    {/* 进口采购 */}
                    <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                            <Truck className="w-4 h-4"/> {t("dashboard.import")}
                        </h3>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <StatCard icon={<Truck className="w-5 h-5 text-sky-500"/>} label={t("dashboard.batches")} value={data.import_summary.total_batches} color="bg-sky-50 border-sky-200"
                                      onClick={() => openHistory(t("dashboard.batches"), "customs")}/>
                            <StatCard icon={<Truck className="w-5 h-5 text-sky-500"/>} label={t("dashboard.invoices")} value={data.import_summary.total_invoices} color="bg-sky-50 border-sky-200"
                                      onClick={() => openHistory(t("dashboard.invoices"), "customs")}/>
                            <StatCard icon={<Truck className="w-5 h-5 text-sky-500"/>} label={t("dashboard.total_amount")} value={agg.importAmount} unit={display.currency} color="bg-sky-50 border-sky-200"
                                      onClick={() => openDetail(t("dashboard.total_amount"), "import", "customs_record", "EUR")}/>
                            <StatCard icon={<Truck className="w-5 h-5 text-sky-500"/>} label={t("dashboard.total_volume")} value={agg.importVolume} unit={unitLabel(display.volume)} color="bg-sky-50 border-sky-200"
                                      onClick={() => openDetail(t("dashboard.total_volume"), "import", "customs_record", "m3")}/>
                        </div>
                        {Object.keys(data.import_summary.suppliers).length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-2">
                                {Object.entries(data.import_summary.suppliers).map(([name, count]) => (
                                    <span key={name} className="px-2.5 py-1 bg-sky-100 text-sky-800 rounded-full text-xs font-medium">{name} ({count})</span>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* 原木进销存 */}
                    <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                            <TreePine className="w-4 h-4"/> {t("dashboard.log")}
                        </h3>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <StatCard icon={<ArrowDownCircle className="w-5 h-5 text-emerald-500"/>} label={t("dashboard.inbound_logs")} value={data.log_summary.total_inbound_logs} unit={t("dashboard.unit_log")} color="bg-emerald-50 border-emerald-200"
                                      onClick={() => openDetail(t("dashboard.inbound_logs"), "log_inbound", "inbound_batch", "m3")}/>
                            <StatCard icon={<ArrowDownCircle className="w-5 h-5 text-emerald-500"/>} label={t("dashboard.inbound_volume")} value={agg.inboundVolume} unit={unitLabel(display.volume)} color="bg-emerald-50 border-emerald-200"
                                      onClick={() => openDetail(t("dashboard.inbound_volume"), "log_inbound", "inbound_batch", "m3")}/>
                            <StatCard icon={<ArrowUpCircle className="w-5 h-5 text-orange-500"/>} label={t("dashboard.outbound_logs")} value={data.log_summary.total_outbound_logs} unit={t("dashboard.unit_log")} color="bg-orange-50 border-orange-200"
                                      onClick={() => openDetail(t("dashboard.outbound_logs"), "log_outbound", "outbound_batch", "m3")}/>
                            <StatCard icon={<ArrowUpCircle className="w-5 h-5 text-orange-500"/>} label={t("dashboard.outbound_volume")} value={agg.outboundVolume} unit={unitLabel(display.volume)} color="bg-orange-50 border-orange-200"
                                      onClick={() => openDetail(t("dashboard.outbound_volume"), "log_outbound", "outbound_batch", "m3")}/>
                        </div>
                        {(agg.inboundVolume > 0 || agg.outboundVolume > 0) && (
                            <div className="mt-3 p-3 bg-gray-50 rounded-lg text-sm">
                                <span className="text-gray-600">{t("dashboard.stock")}</span>
                                <span className="font-bold text-gray-900 ml-1">{fmtNum(agg.inboundVolume - agg.outboundVolume)} {unitLabel(display.volume)}</span>
                                <span className="text-gray-500 ml-2">({data.log_summary.total_inbound_logs - data.log_summary.total_outbound_logs} {t("dashboard.unit_log")})</span>
                            </div>
                        )}
                    </div>

                    {/* 工厂加工 */}
                    <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                            <Scissors className="w-4 h-4"/> {t("dashboard.factory")}
                        </h3>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                            <StatCard icon={<Package className="w-5 h-5 text-violet-500"/>} label={t("dashboard.soak_pool")}
                                      value={`${data.factory_summary.soak_pool_logs} ${t("dashboard.unit_log")}`}
                                      unit={agg.soakVolume > 0 ? `/ ${fmtNum(agg.soakVolume)} ${unitLabel(display.volume)}` : undefined}
                                      color="bg-violet-50 border-violet-200"
                                      onClick={() => openDetail(t("dashboard.soak_pool"), "soak_pool", "soak_pool_batch", t("dashboard.unit_log"))}/>
                            <StatCard icon={<Scissors className="w-5 h-5 text-rose-500"/>} label={t("dashboard.slicing")}
                                      value={`${data.factory_summary.slicing_logs} ${t("dashboard.unit_log")}`}
                                      unit={agg.slicingArea > 0 ? `/ ${fmtNum(agg.slicingArea)} ${unitLabel(display.area)}` : undefined}
                                      color="bg-rose-50 border-rose-200"
                                      onClick={() => openDetail(t("dashboard.slicing"), "slicing", "slicing_batch", t("dashboard.unit_log"))}/>
                            <StatCard icon={<Package className="w-5 h-5 text-teal-500"/>} label={t("dashboard.packing")}
                                      value={`${data.factory_summary.packing_packages} ${t("dashboard.unit_pack")}`}
                                      unit={`/ ${data.factory_summary.packing_pieces} ${t("dashboard.unit_piece")} / ${fmtNum(agg.packingArea)} ${unitLabel(display.area)}`}
                                      color="bg-teal-50 border-teal-200"
                                      onClick={() => openDetail(t("dashboard.packing"), "packing", "packing_batch", t("dashboard.unit_pack"))}/>
                        </div>
                    </div>

                    {/* 空数据提示 */}
                    {data.total_documents_processed === 0 && (
                        <div className="text-center py-10 text-gray-400">
                            <BarChart3 className="w-12 h-12 mx-auto mb-3"/>
                            <p className="text-lg">{t("dashboard.empty")}</p>
                            <p className="text-sm">{t("dashboard.empty_hint")}</p>
                        </div>
                    )}
                </div>
            ) : null}
        </div>
        </>
    );
}
