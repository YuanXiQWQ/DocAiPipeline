import React, {useState, useEffect, useCallback} from "react";
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
    RefreshCw,
} from "lucide-react";
import {
    getSummary,
    getSummaryEntries,
    createSummaryEntry,
    updateSummaryEntry,
    deleteSummaryEntry,
    restoreSummaryEntry,
    getExchangeRates,
    extractErrorMessage,
    type OverallSummary,
    type SummaryEntry,
} from "./api";
import {useT} from "./i18n";

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

type LengthUnit = "mm" | "cm" | "m" | "in" | "ft";
type AreaUnit = "mm²" | "cm²" | "m²" | "in²" | "ft²";
type VolumeUnit = "mm³" | "cm³" | "m³" | "in³" | "ft³";
type CurrencyUnit = "EUR" | "USD" | "CNY" | "RSD";

interface UnitConfig {
    length: LengthUnit;
    area: AreaUnit;
    volume: VolumeUnit;
    currency: CurrencyUnit;
}

const LENGTH_TO_M: Record<LengthUnit, number> = { mm: 0.001, cm: 0.01, m: 1, in: 0.0254, ft: 0.3048 };
const AREA_TO_M2: Record<AreaUnit, number> = { "mm²": 1e-6, "cm²": 1e-4, "m²": 1, "in²": 0.00064516, "ft²": 0.092903 };
const VOL_TO_M3: Record<VolumeUnit, number> = { "mm³": 1e-9, "cm³": 1e-6, "m³": 1, "in³": 1.6387e-5, "ft³": 0.0283168 };

const LENGTH_UNITS: LengthUnit[] = ["mm", "cm", "m", "in", "ft"];
const AREA_UNITS: AreaUnit[] = ["mm²", "cm²", "m²", "in²", "ft²"];
const VOLUME_UNITS: VolumeUnit[] = ["mm³", "cm³", "m³", "in³", "ft³"];
const CURRENCY_UNITS: CurrencyUnit[] = ["EUR", "USD", "CNY", "RSD"];

const DEFAULT_UNITS: UnitConfig = { length: "m", area: "m²", volume: "m³", currency: "EUR" };

/** 单位换算：将原始值从原始单位转换到目标单位（仅视觉展示） */
function convertUnit(value: number, fromUnit: string, units: UnitConfig, rates: Record<string, number>): { value: number; unit: string } {
    const fu = fromUnit.toLowerCase().trim();
    // 货币
    if (fu === "eur" || fu === "usd" || fu === "cny" || fu === "rsd") {
        if (units.currency === fromUnit.toUpperCase()) return {value, unit: units.currency};
        const fromKey = fu;
        const toKey = units.currency.toLowerCase();
        const fromToEur = fromKey === "eur" ? 1 : (1 / (rates[fromKey] || 1));
        const eurToTarget = toKey === "eur" ? 1 : (rates[toKey] || 1);
        return {value: value * fromToEur * eurToTarget, unit: units.currency};
    }
    // 体积
    if (fu === "m³" || fu === "cm³" || fu === "mm³" || fu === "in³" || fu === "ft³") {
        const fromFactor = VOL_TO_M3[fu as VolumeUnit] ?? 1;
        const toFactor = VOL_TO_M3[units.volume] ?? 1;
        return {value: value * fromFactor / toFactor, unit: units.volume};
    }
    // 面积
    if (fu === "m²" || fu === "cm²" || fu === "mm²" || fu === "in²" || fu === "ft²") {
        const fromFactor = AREA_TO_M2[fu as AreaUnit] ?? 1;
        const toFactor = AREA_TO_M2[units.area] ?? 1;
        return {value: value * fromFactor / toFactor, unit: units.area};
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
    onBack: () => void;
}

function DetailView({title, category, metric, dateFrom, dateTo, unit, onBack}: DetailViewProps) {
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
    /* 新增行 */
    const [addAfter, setAddAfter] = useState<string | null>(null);
    const [newValue, setNewValue] = useState("");
    const [newDate, setNewDate] = useState("");
    const [newNote, setNewNote] = useState("");

    const fetchEntries = useCallback(() => {
        setLoading(true);
        getSummaryEntries({
            date_from: dateFrom, date_to: dateTo,
            category, metric,
            include_deleted: showDeleted,
        })
            .then(r => setEntries(r.entries))
            .finally(() => setLoading(false));
    }, [dateFrom, dateTo, category, metric, showDeleted]);

    useEffect(() => { fetchEntries(); }, [fetchEntries]);

    const totalValue = entries
        .filter(e => !e.deleted)
        .reduce((s, e) => s + e.value, 0);

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
            value: v, unit,
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
                <button onClick={onBack} className="flex items-center gap-1 text-sm text-blue-600 hover:underline">
                    <ArrowLeft className="w-4 h-4"/> {t("dashboard.back")}
                </button>
                <div className="flex items-center gap-2">
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
                <p className="text-3xl font-bold text-gray-900">{fmtNum(totalValue)} <span className="text-base font-normal text-gray-500">{unit}</span></p>
            </div>

            {/* 明细表格 */}
            {loading ? (
                <div className="flex justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-blue-500"/></div>
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
                            <th className="px-4 py-2.5 text-left font-medium">{t("dashboard.source_file")}</th>
                            <th className="px-4 py-2.5 text-right font-medium">{t("dashboard.entry_value")}</th>
                            <th className="px-4 py-2.5 text-center font-medium w-32"></th>
                        </tr>
                        </thead>
                        <tbody>
                        {entries.map((entry) => (
                            <React.Fragment key={entry.id}>
                                <tr className={`border-t border-gray-100 ${entry.deleted ? "bg-gray-50 opacity-50" : ""} ${editingRow === entry.id ? "bg-blue-50" : ""}`}>
                                    <td className="px-4 py-2.5">
                                        {editingRow === entry.id ? (
                                            <input type="date" value={editDate} onChange={e => setEditDate(e.target.value)} className="border rounded px-2 py-1 text-xs w-36"/>
                                        ) : (
                                            <span className="text-gray-700">{entry.date}</span>
                                        )}
                                    </td>
                                    <td className="px-4 py-2.5 text-gray-600 truncate max-w-[200px]">
                                        <span className={`inline-block px-1.5 py-0.5 rounded text-xs mr-1.5 ${
                                            entry.source === "manual" ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700"
                                        }`}>{entry.source === "manual" ? t("dashboard.manual_entry") : t("dashboard.auto_entry")}</span>
                                        {entry.filename || "—"}
                                    </td>
                                    <td className="px-4 py-2.5 text-right font-mono">
                                        {editingRow === entry.id ? (
                                            <input type="number" step="any" value={editValue} onChange={e => setEditValue(e.target.value)} className="border rounded px-2 py-1 text-xs w-28 text-right"/>
                                        ) : (
                                            <span className={entry.deleted ? "line-through" : ""}>{fmtNum(entry.value)} {unit}</span>
                                        )}
                                    </td>
                                    <td className="px-4 py-2.5 text-center">
                                        <div className="flex items-center justify-center gap-1">
                                            {/* 编辑历史标记 */}
                                            {entry.revisions.length > 0 && (
                                                <button onClick={() => toggleHistory(entry.id)} className="p-1 text-gray-400 hover:text-blue-500" title={t("dashboard.history")}>
                                                    <Clock className="w-3.5 h-3.5"/>
                                                </button>
                                            )}
                                            {editing && !entry.deleted && editingRow !== entry.id && (
                                                <>
                                                    <button onClick={() => { setEditingRow(entry.id); setEditValue(String(entry.value)); setEditDate(entry.date); setEditNote(""); }}
                                                            className="p-1 text-gray-400 hover:text-blue-500" title={t("dashboard.edit_mode")}>
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
                                        <td colSpan={4} className="bg-slate-50 px-6 py-3">
                                            <p className="text-xs font-medium text-gray-500 mb-2">{t("dashboard.history")}</p>
                                            <div className="space-y-1.5">
                                                {entry.revisions.map((rev) => (
                                                    <div key={rev.revision_id} className="text-xs text-gray-500 flex gap-3">
                                                        <span className="text-gray-400 whitespace-nowrap">{rev.timestamp.slice(0, 16).replace("T", " ")}</span>
                                                        <span className={`px-1.5 py-0.5 rounded ${rev.author === "user" ? "bg-amber-50 text-amber-600" : "bg-blue-50 text-blue-600"}`}>{rev.author}</span>
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
                                        <td className="px-4 py-2.5 text-xs text-amber-600">{t("dashboard.manual_entry")}</td>
                                        <td className="px-4 py-2.5">
                                            <input type="number" step="any" placeholder={t("dashboard.entry_value")} value={newValue} onChange={e => setNewValue(e.target.value)}
                                                   className="border rounded px-2 py-1 text-xs w-28 text-right"/>
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
/* 主看板                                                         */
/* ============================================================== */

/* ============================================================== */
/* 筛选面板（展开式）                                              */
/* ============================================================== */

function FilterPanel({
    dateFrom, dateTo, setDateFrom, setDateTo,
    units, setUnits,
    rates, ratesLive, onRefreshRates,
    onReset,
}: {
    dateFrom: string; dateTo: string;
    setDateFrom: (v: string) => void; setDateTo: (v: string) => void;
    units: UnitConfig; setUnits: (u: UnitConfig) => void;
    rates: Record<string, number>; ratesLive: boolean; onRefreshRates: () => void;
    onReset: () => void;
}) {
    const t = useT();
    const [defFrom, defTo] = thisYearRange();
    return (
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            {/* 第一行：日期范围 */}
            <div className="flex flex-wrap items-end gap-4">
                <div>
                    <label className="block text-xs text-gray-500 mb-1">{t("dashboard.date_from")}</label>
                    <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                           className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"/>
                </div>
                <div>
                    <label className="block text-xs text-gray-500 mb-1">{t("dashboard.date_to")}</label>
                    <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                           className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"/>
                </div>
                <button onClick={() => { setDateFrom(defFrom); setDateTo(defTo); }}
                        className="px-3 py-1.5 border border-gray-200 text-gray-500 text-sm rounded-lg hover:bg-gray-50 transition">
                    {t("dashboard.reset_filter")}
                </button>
            </div>

            {/* 分隔线 */}
            <div className="border-t border-gray-100"/>

            {/* 第二行：单位换算 */}
            <div>
                <p className="text-xs font-medium text-gray-500 mb-2.5">{t("dashboard.unit_conversion")}</p>
                <div className="flex flex-wrap items-center gap-4">
                    {/* 货币 */}
                    <div className="flex items-center gap-1.5">
                        <span className="text-xs text-gray-400">{t("dashboard.currency")}</span>
                        <select value={units.currency}
                                onChange={e => setUnits({...units, currency: e.target.value as CurrencyUnit})}
                                className="border border-gray-200 rounded-lg px-2 py-1 text-sm">
                            {CURRENCY_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                        </select>
                        <button onClick={onRefreshRates} className="p-1 text-gray-400 hover:text-blue-500" title={ratesLive ? t("dashboard.rate_live") : t("dashboard.rate_fallback")}>
                            <RefreshCw className={`w-3.5 h-3.5 ${ratesLive ? "text-emerald-500" : "text-gray-300"}`}/>
                        </button>
                        {ratesLive && units.currency !== "EUR" && rates[units.currency.toLowerCase()] && (
                            <span className="text-xs text-gray-400">1 EUR = {rates[units.currency.toLowerCase()]?.toFixed(2)} {units.currency}</span>
                        )}
                    </div>

                    <div className="h-4 border-l border-gray-200"/>

                    {/* 长度 */}
                    <div className="flex items-center gap-1.5">
                        <span className="text-xs text-gray-400">{t("dashboard.length")}</span>
                        <select value={units.length}
                                onChange={e => {
                                    const l = e.target.value as LengthUnit;
                                    const idx = LENGTH_UNITS.indexOf(l);
                                    setUnits({...units, length: l, area: AREA_UNITS[idx], volume: VOLUME_UNITS[idx]});
                                }}
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
                            {AREA_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                        </select>
                    </div>

                    {/* 体积 */}
                    <div className="flex items-center gap-1.5">
                        <span className="text-xs text-gray-400">{t("dashboard.volume")}</span>
                        <select value={units.volume}
                                onChange={e => setUnits({...units, volume: e.target.value as VolumeUnit})}
                                className="border border-gray-200 rounded-lg px-2 py-1 text-sm">
                            {VOLUME_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                        </select>
                    </div>

                    {/* 重置 */}
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

    /* 单位换算 */
    const [units, setUnits] = useState<UnitConfig>({...DEFAULT_UNITS});
    const [rates, setRates] = useState<Record<string, number>>({});
    const [ratesLive, setRatesLive] = useState(false);

    /* 明细视图状态 */
    const [detailView, setDetailView] = useState<{title: string; category: string; metric: string; unit: string} | null>(null);

    const fetchData = useCallback(() => {
        setLoading(true);
        setError(null);
        getSummary(dateFrom, dateTo)
            .then(setData)
            .catch(err => setError(extractErrorMessage(err)))
            .finally(() => setLoading(false));
    }, [dateFrom, dateTo]);

    const fetchRates = useCallback(() => {
        getExchangeRates("EUR")
            .then(r => { setRates(r.rates); setRatesLive(true); })
            .catch(() => setRatesLive(false));
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);
    useEffect(() => { fetchRates(); }, [fetchRates]);

    /* 换算辅助函数 */
    const cv = useCallback((value: number, fromUnit: string) => {
        return convertUnit(value, fromUnit, units, rates);
    }, [units, rates]);

    const cvFmt = useCallback((value: number, fromUnit: string) => {
        const r = cv(value, fromUnit);
        return {text: fmtNum(r.value), unit: r.unit};
    }, [cv]);

    const openDetail = (title: string, category: string, metric: string, unit: string) => {
        setDetailView({title, category, metric, unit});
    };

    const resetAll = () => {
        setDateFrom(defFrom);
        setDateTo(defTo);
        setUnits({...DEFAULT_UNITS});
    };

    /* 明细视图 */
    if (detailView) {
        return (
            <div className="space-y-6">
                <div className="flex items-center gap-3 mb-2">
                    <BarChart3 className="w-6 h-6 text-blue-600"/>
                    <h2 className="text-xl font-semibold text-gray-900">{t("dashboard.detail_title")}</h2>
                </div>
                <DetailView
                    title={detailView.title}
                    category={detailView.category}
                    metric={detailView.metric}
                    dateFrom={dateFrom}
                    dateTo={dateTo}
                    unit={detailView.unit}
                    onBack={() => { setDetailView(null); fetchData(); }}
                />
            </div>
        );
    }

    /* 主看板视图 */
    return (
        <div className="space-y-8">
            <div className="flex items-center gap-3">
                <BarChart3 className="w-6 h-6 text-blue-600"/>
                <h2 className="text-xl font-semibold text-gray-900">{t("dashboard.title")}</h2>
            </div>

            {/* 展开式筛选面板 */}
            <FilterPanel
                dateFrom={dateFrom} dateTo={dateTo}
                setDateFrom={setDateFrom} setDateTo={setDateTo}
                units={units} setUnits={setUnits}
                rates={rates} ratesLive={ratesLive} onRefreshRates={fetchRates}
                onReset={resetAll}
            />

            {loading ? (
                <div className="flex items-center justify-center py-20">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500"/>
                </div>
            ) : error ? (
                <div className="text-center py-20 text-red-500">{error}</div>
            ) : data ? (
                <div className="space-y-8">
                    {/* 总览 */}
                    <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">{t("dashboard.overview")}</h3>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <StatCard icon={<BarChart3 className="w-5 h-5 text-blue-500"/>} label={t("dashboard.docs_processed")} value={data.total_documents_processed} unit={t("dashboard.unit_doc")} color="bg-blue-50 border-blue-200"/>
                            <StatCard icon={<BarChart3 className="w-5 h-5 text-indigo-500"/>} label={t("dashboard.pages_processed")} value={data.total_pages_processed} unit={t("dashboard.unit_page")} color="bg-indigo-50 border-indigo-200"/>
                            <StatCard icon={<ArrowDownCircle className="w-5 h-5 text-emerald-500"/>} label={t("dashboard.log_inbound")} value={cv(data.log_summary.total_inbound_m3, "m³").value} unit={cv(data.log_summary.total_inbound_m3, "m³").unit} color="bg-emerald-50 border-emerald-200"
                                      onClick={() => openDetail(t("dashboard.inbound_volume"), "log_inbound", "inbound_batch", "m³")}/>
                            <StatCard icon={<ArrowUpCircle className="w-5 h-5 text-amber-500"/>} label={t("dashboard.log_outbound")} value={cv(data.log_summary.total_outbound_m3, "m³").value} unit={cv(data.log_summary.total_outbound_m3, "m³").unit} color="bg-amber-50 border-amber-200"
                                      onClick={() => openDetail(t("dashboard.outbound_volume"), "log_outbound", "outbound_batch", "m³")}/>
                        </div>
                    </div>

                    {/* 进口采购 */}
                    <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                            <Truck className="w-4 h-4"/> {t("dashboard.import")}
                        </h3>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <StatCard icon={<Truck className="w-5 h-5 text-sky-500"/>} label={t("dashboard.batches")} value={data.import_summary.total_batches} color="bg-sky-50 border-sky-200"/>
                            <StatCard icon={<Truck className="w-5 h-5 text-sky-500"/>} label={t("dashboard.invoices")} value={data.import_summary.total_invoices} color="bg-sky-50 border-sky-200"/>
                            <StatCard icon={<Truck className="w-5 h-5 text-sky-500"/>} label={t("dashboard.total_amount")} value={cv(data.import_summary.total_amount_eur, "EUR").value} unit={cv(data.import_summary.total_amount_eur, "EUR").unit} color="bg-sky-50 border-sky-200"
                                      onClick={() => openDetail(t("dashboard.total_amount"), "import", "customs_record", "EUR")}/>
                            <StatCard icon={<Truck className="w-5 h-5 text-sky-500"/>} label={t("dashboard.total_volume")} value={cv(data.import_summary.total_volume_m3, "m³").value} unit={cv(data.import_summary.total_volume_m3, "m³").unit} color="bg-sky-50 border-sky-200"/>
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
                                      onClick={() => openDetail(t("dashboard.inbound_logs"), "log_inbound", "inbound_batch", "m³")}/>
                            <StatCard icon={<ArrowDownCircle className="w-5 h-5 text-emerald-500"/>} label={t("dashboard.inbound_volume")} value={cv(data.log_summary.total_inbound_m3, "m³").value} unit={cv(data.log_summary.total_inbound_m3, "m³").unit} color="bg-emerald-50 border-emerald-200"
                                      onClick={() => openDetail(t("dashboard.inbound_volume"), "log_inbound", "inbound_batch", "m³")}/>
                            <StatCard icon={<ArrowUpCircle className="w-5 h-5 text-orange-500"/>} label={t("dashboard.outbound_logs")} value={data.log_summary.total_outbound_logs} unit={t("dashboard.unit_log")} color="bg-orange-50 border-orange-200"
                                      onClick={() => openDetail(t("dashboard.outbound_logs"), "log_outbound", "outbound_batch", "m³")}/>
                            <StatCard icon={<ArrowUpCircle className="w-5 h-5 text-orange-500"/>} label={t("dashboard.outbound_volume")} value={cv(data.log_summary.total_outbound_m3, "m³").value} unit={cv(data.log_summary.total_outbound_m3, "m³").unit} color="bg-orange-50 border-orange-200"
                                      onClick={() => openDetail(t("dashboard.outbound_volume"), "log_outbound", "outbound_batch", "m³")}/>
                        </div>
                        {(data.log_summary.total_inbound_m3 > 0 || data.log_summary.total_outbound_m3 > 0) && (
                            <div className="mt-3 p-3 bg-gray-50 rounded-lg text-sm">
                                <span className="text-gray-600">{t("dashboard.stock")}</span>
                                <span className="font-bold text-gray-900 ml-1">{fmtNum(cv(data.log_summary.total_inbound_m3 - data.log_summary.total_outbound_m3, "m³").value)} {cv(0, "m³").unit}</span>
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
                                      unit={data.factory_summary.soak_pool_m3 > 0 ? `/ ${fmtNum(cv(data.factory_summary.soak_pool_m3, "m³").value)} ${cv(0, "m³").unit}` : undefined}
                                      color="bg-violet-50 border-violet-200"
                                      onClick={() => openDetail(t("dashboard.soak_pool"), "soak_pool", "soak_pool_batch", "根")}/>
                            <StatCard icon={<Scissors className="w-5 h-5 text-rose-500"/>} label={t("dashboard.slicing")}
                                      value={`${data.factory_summary.slicing_logs} ${t("dashboard.unit_log")}`}
                                      unit={data.factory_summary.slicing_output_m2 > 0 ? `/ ${fmtNum(cv(data.factory_summary.slicing_output_m2, "m²").value)} ${cv(0, "m²").unit}` : undefined}
                                      color="bg-rose-50 border-rose-200"
                                      onClick={() => openDetail(t("dashboard.slicing"), "slicing", "slicing_batch", "根")}/>
                            <StatCard icon={<Package className="w-5 h-5 text-teal-500"/>} label={t("dashboard.packing")}
                                      value={`${data.factory_summary.packing_packages} ${t("dashboard.unit_pack")}`}
                                      unit={`/ ${data.factory_summary.packing_pieces} ${t("dashboard.unit_piece")} / ${fmtNum(cv(data.factory_summary.packing_area_m2, "m²").value)} ${cv(0, "m²").unit}`}
                                      color="bg-teal-50 border-teal-200"
                                      onClick={() => openDetail(t("dashboard.packing"), "packing", "packing_batch", "包")}/>
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
    );
}
