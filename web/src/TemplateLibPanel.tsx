import React, {useState, useEffect, useCallback, useRef} from "react";
import {
    Plus,
    Upload,
    Filter,
    Settings2,
    Star,
    Trash2,
    Download,
    X,
    CheckSquare,
    Square,
    Loader2,
    FileSpreadsheet,
    Tag,
} from "lucide-react";
import {
    listTemplates,
    importTemplate,
    deleteTemplates,
    setTemplateDefault,
    getTemplateDownloadUrl,
    previewTemplate,
    recommendTemplateTypes,
    extractErrorMessage,
    DOC_TYPE_KEYS,
    type TemplateRecord,
} from "./api";
import {useT} from "./i18n";

// ------------------------------------------------------------------
// 辅助
// ------------------------------------------------------------------

function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(iso: string): string {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleString();
    } catch {
        return iso;
    }
}

/** 所有文档类型（不含 auto） */
const ALL_TYPES = Object.keys(DOC_TYPE_KEYS).filter((k) => k !== "auto");

// ------------------------------------------------------------------
// 模板库面板
// ------------------------------------------------------------------

export default function TemplateLibPanel() {
    const t = useT();

    // 数据
    const [templates, setTemplates] = useState<TemplateRecord[]>([]);
    const [loading, setLoading] = useState(true);

    // 视图控制
    const [sortBy, setSortBy] = useState<"last_used_at" | "imported_at" | "name">("last_used_at");
    const [categoryView, setCategoryView] = useState(false);
    const [manageMode, setManageMode] = useState(false);
    const [prefMode, setPrefMode] = useState(false);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [filterOpen, setFilterOpen] = useState(false);

    // 导入
    const [importing, setImporting] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // 预览
    const [previewId, setPreviewId] = useState<string | null>(null);
    const [previewData, setPreviewData] = useState<any>(null);
    const [previewLoading, setPreviewLoading] = useState(false);

    // 获取数据
    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const data = await listTemplates({sort_by: sortBy});
            setTemplates(data);
        } catch (err) {
            console.error("加载模板列表失败:", extractErrorMessage(err));
        } finally {
            setLoading(false);
        }
    }, [sortBy]);

    useEffect(() => {
        void fetchData();
    }, [fetchData]);

    // 导入模板文件
    const handleImport = async (files: FileList | null) => {
        if (!files || files.length === 0) return;
        setImporting(true);
        try {
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                // 先获取推荐类型
                let types: string[] = [];
                try {
                    const rec = await recommendTemplateTypes(file);
                    types = rec.recommended;
                } catch { /* 推荐失败则不指定类型 */ }
                await importTemplate(file, undefined, types);
            }
            await fetchData();
        } catch (err) {
            alert("导入失败: " + extractErrorMessage(err));
        } finally {
            setImporting(false);
            if (fileInputRef.current) fileInputRef.current.value = "";
        }
    };

    // 拖放导入
    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        const files = e.dataTransfer.files;
        const xlsxFiles = Array.from(files).filter((f) => f.name.endsWith(".xlsx"));
        if (xlsxFiles.length > 0) {
            const dt = new DataTransfer();
            xlsxFiles.forEach((f) => dt.items.add(f));
            void handleImport(dt.files);
        }
    };

    // 批量删除
    const handleBatchDelete = async () => {
        if (selected.size === 0) return;
        // 过滤内置模板
        const deletable = [...selected].filter((id) => {
            const tpl = templates.find((t) => t.id === id);
            return tpl && !tpl.builtin;
        });
        if (deletable.length === 0) {
            alert(t("template_lib.cannot_delete_builtin"));
            return;
        }
        if (!confirm(t("template_lib.confirm_delete").replace("{n}", String(deletable.length)))) return;
        try {
            await deleteTemplates(deletable);
            setSelected(new Set());
            await fetchData();
        } catch (err) {
            alert("删除失败: " + extractErrorMessage(err));
        }
    };

    // 设置/取消默认
    const handleToggleDefault = async (tplId: string, docType: string, currentlyDefault: boolean) => {
        try {
            await setTemplateDefault(tplId, docType, !currentlyDefault);
            await fetchData();
        } catch (err) {
            console.error("设置默认失败:", extractErrorMessage(err));
        }
    };

    // 预览
    const handlePreview = async (id: string) => {
        setPreviewId(id);
        setPreviewLoading(true);
        try {
            const data = await previewTemplate(id);
            setPreviewData(data);
        } catch (err) {
            setPreviewData(null);
            alert("预览失败: " + extractErrorMessage(err));
        } finally {
            setPreviewLoading(false);
        }
    };

    // 按类型分组
    const groupByType = (): Record<string, TemplateRecord[]> => {
        const groups: Record<string, TemplateRecord[]> = {};
        for (const type of ALL_TYPES) {
            groups[type] = templates.filter((tpl) => tpl.types.includes(type));
        }
        return groups;
    };

    // ------------------------------------------------------------------
    // 渲染
    // ------------------------------------------------------------------

    const renderCard = (tpl: TemplateRecord, contextType?: string) => {
        const isSelected = selected.has(tpl.id);
        const isDefault = contextType ? tpl.default_for.includes(contextType) : false;

        return (
            <div
                key={`${tpl.id}-${contextType || ""}`}
                className={`relative rounded-lg border p-4 cursor-pointer transition-all hover:shadow-md ${
                    isDefault ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white"
                } ${isSelected ? "ring-2 ring-blue-500" : ""}`}
                onClick={() => {
                    if (manageMode) {
                        const next = new Set(selected);
                        if (next.has(tpl.id)) next.delete(tpl.id);
                        else next.add(tpl.id);
                        setSelected(next);
                    } else if (prefMode && contextType) {
                        void handleToggleDefault(tpl.id, contextType, isDefault);
                    } else {
                        void handlePreview(tpl.id);
                    }
                }}
            >
                {/* 管理模式选框 */}
                {manageMode && (
                    <div className="absolute top-2 right-2">
                        {isSelected ? (
                            <CheckSquare className="w-5 h-5 text-blue-500"/>
                        ) : (
                            <Square className="w-5 h-5 text-gray-400"/>
                        )}
                    </div>
                )}

                {/* 默认标记 */}
                {isDefault && !manageMode && (
                    <Star className="absolute top-2 right-2 w-4 h-4 text-yellow-500 fill-yellow-400"/>
                )}

                {/* 内置标记 */}
                {tpl.builtin && (
                    <span className="absolute top-2 left-2 text-[10px] px-1.5 py-0.5 bg-green-100 text-green-700 rounded">
                        {t("template_lib.builtin")}
                    </span>
                )}

                {/* 图标 */}
                <div className="flex items-center justify-center mb-3 mt-3">
                    <FileSpreadsheet className="w-10 h-10 text-green-600"/>
                </div>

                {/* 名称 */}
                <p className="text-sm font-medium text-center truncate" title={tpl.name}>
                    {tpl.name}
                </p>

                {/* 类型标签 */}
                <div className="flex flex-wrap gap-1 justify-center mt-2">
                    {tpl.types.slice(0, 3).map((tp) => (
                        <span key={tp} className="text-[10px] px-1 py-0.5 bg-gray-100 text-gray-600 rounded">
                            {t(DOC_TYPE_KEYS[tp] || tp)}
                        </span>
                    ))}
                    {tpl.types.length > 3 && (
                        <span className="text-[10px] text-gray-400">+{tpl.types.length - 3}</span>
                    )}
                </div>

                {/* 元信息 */}
                <div className="mt-2 text-[10px] text-gray-400 text-center">
                    {formatSize(tpl.size_bytes)} · {formatTime(tpl.imported_at).split(" ")[0]}
                </div>
            </div>
        );
    };

    const renderAddCard = (onClick: () => void) => (
        <div
            className="rounded-lg border-2 border-dashed border-gray-300 p-4 flex flex-col items-center justify-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-all min-h-[180px]"
            onClick={onClick}
        >
            <Plus className="w-8 h-8 text-gray-400"/>
            <span className="text-xs text-gray-400 mt-2">{t("template_lib.add")}</span>
        </div>
    );

    // 时间排序视图（默认）
    const renderFlatView = () => (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {!manageMode && !prefMode && renderAddCard(() => fileInputRef.current?.click())}
            {templates.map((tpl) => renderCard(tpl))}
        </div>
    );

    // 分类视图
    const renderCategoryView = () => {
        const groups = groupByType();
        return (
            <div className="space-y-6">
                {ALL_TYPES.map((type) => (
                    <div key={type}>
                        <h3 className="text-sm font-semibold text-gray-700 mb-2 border-b pb-1">
                            <Tag className="w-3.5 h-3.5 inline mr-1"/>
                            {t(DOC_TYPE_KEYS[type] || type)}
                        </h3>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                            {!manageMode && !prefMode && renderAddCard(() => fileInputRef.current?.click())}
                            {groups[type].map((tpl) => renderCard(tpl, type))}
                        </div>
                    </div>
                ))}
            </div>
        );
    };

    // 预览弹窗
    const renderPreviewModal = () => {
        if (!previewId) return null;
        const tpl = templates.find((t) => t.id === previewId);
        return (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setPreviewId(null)}>
                <div
                    className="bg-white rounded-xl shadow-2xl w-[90%] max-w-4xl max-h-[80vh] overflow-hidden flex flex-col"
                    onClick={(e) => e.stopPropagation()}
                >
                    {/* 头部 */}
                    <div className="flex items-center justify-between p-4 border-b">
                        <div>
                            <h3 className="font-semibold">{tpl?.name || ""}</h3>
                            <p className="text-xs text-gray-400">{tpl?.filename}</p>
                        </div>
                        <div className="flex gap-2">
                            {tpl && (
                                <a
                                    href={getTemplateDownloadUrl(tpl.id)}
                                    className="p-2 rounded hover:bg-gray-100"
                                    title={t("template_lib.download")}
                                >
                                    <Download className="w-4 h-4"/>
                                </a>
                            )}
                            <button className="p-2 rounded hover:bg-gray-100" onClick={() => setPreviewId(null)}>
                                <X className="w-4 h-4"/>
                            </button>
                        </div>
                    </div>

                    {/* 内容 */}
                    <div className="flex-1 overflow-auto p-4">
                        {previewLoading && (
                            <div className="flex items-center justify-center h-40">
                                <Loader2 className="w-6 h-6 animate-spin text-blue-500"/>
                            </div>
                        )}
                        {!previewLoading && previewData && (
                            <div className="space-y-4">
                                {previewData.sheet_names.map((sn: string) => {
                                    const sheet = previewData.sheets[sn];
                                    if (!sheet) return null;
                                    return (
                                        <div key={sn}>
                                            <h4 className="text-sm font-medium mb-1 text-gray-700">
                                                {sn}
                                                <span className="text-xs text-gray-400 ml-2">
                                                    ({sheet.total_rows}行 × {sheet.total_cols}列)
                                                </span>
                                            </h4>
                                            <div className="overflow-x-auto border rounded">
                                                <table className="text-xs min-w-full">
                                                    <thead className="bg-gray-50">
                                                        <tr>
                                                            {sheet.headers.map((h: any, i: number) => (
                                                                <th key={i} className="px-2 py-1 text-left whitespace-nowrap border-b">
                                                                    {h ?? ""}
                                                                </th>
                                                            ))}
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {sheet.rows.map((row: any[], ri: number) => (
                                                            <tr key={ri} className="border-b last:border-0">
                                                                {row.map((cell, ci) => (
                                                                    <td key={ci} className="px-2 py-1 whitespace-nowrap">
                                                                        {cell ?? ""}
                                                                    </td>
                                                                ))}
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        );
    };

    return (
        <div
            className="p-6 max-w-7xl mx-auto"
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
        >
            {/* 工具栏 */}
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-bold">{t("template_lib.title")}</h2>
                <div className="flex items-center gap-2">
                    {/* 首选项（分类视图下可用） */}
                    {categoryView && (
                        <button
                            className={`p-2 rounded-lg transition ${prefMode ? "bg-yellow-100 text-yellow-700" : "hover:bg-gray-100 text-gray-600"}`}
                            onClick={() => { setPrefMode(!prefMode); setManageMode(false); }}
                            title={t("template_lib.preferences")}
                        >
                            <Star className="w-4 h-4"/>
                        </button>
                    )}

                    {/* 导入 */}
                    <button
                        className="p-2 rounded-lg hover:bg-gray-100 text-gray-600"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={importing}
                        title={t("template_lib.import")}
                    >
                        {importing ? <Loader2 className="w-4 h-4 animate-spin"/> : <Upload className="w-4 h-4"/>}
                    </button>

                    {/* 过滤器 */}
                    <div className="relative">
                        <button
                            className={`p-2 rounded-lg transition ${filterOpen ? "bg-blue-100 text-blue-700" : "hover:bg-gray-100 text-gray-600"}`}
                            onClick={() => setFilterOpen(!filterOpen)}
                            title={t("template_lib.filter")}
                        >
                            <Filter className="w-4 h-4"/>
                        </button>
                        {filterOpen && (
                            <div className="absolute right-0 top-10 bg-white border rounded-lg shadow-lg p-3 z-10 w-48 space-y-2">
                                <label className="flex items-center gap-2 text-xs cursor-pointer">
                                    <input
                                        type="radio"
                                        name="sort"
                                        checked={sortBy === "last_used_at"}
                                        onChange={() => setSortBy("last_used_at")}
                                    />
                                    {t("template_lib.sort_last_used")}
                                </label>
                                <label className="flex items-center gap-2 text-xs cursor-pointer">
                                    <input
                                        type="radio"
                                        name="sort"
                                        checked={sortBy === "imported_at"}
                                        onChange={() => setSortBy("imported_at")}
                                    />
                                    {t("template_lib.sort_imported")}
                                </label>
                                <label className="flex items-center gap-2 text-xs cursor-pointer">
                                    <input
                                        type="radio"
                                        name="sort"
                                        checked={sortBy === "name"}
                                        onChange={() => setSortBy("name")}
                                    />
                                    {t("template_lib.sort_name")}
                                </label>
                                <hr/>
                                <label className="flex items-center gap-2 text-xs cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={categoryView}
                                        onChange={(e) => setCategoryView(e.target.checked)}
                                    />
                                    {t("template_lib.category_view")}
                                </label>
                            </div>
                        )}
                    </div>

                    {/* 管理 */}
                    <button
                        className={`p-2 rounded-lg transition ${manageMode ? "bg-red-100 text-red-700" : "hover:bg-gray-100 text-gray-600"}`}
                        onClick={() => { setManageMode(!manageMode); setPrefMode(false); setSelected(new Set()); }}
                        title={t("template_lib.manage")}
                    >
                        <Settings2 className="w-4 h-4"/>
                    </button>
                </div>
            </div>

            {/* 管理模式操作栏 */}
            {manageMode && selected.size > 0 && (
                <div className="mb-4 flex items-center gap-3 p-3 bg-red-50 rounded-lg">
                    <span className="text-sm text-red-700">
                        {t("template_lib.selected").replace("{n}", String(selected.size))}
                    </span>
                    <button
                        className="flex items-center gap-1 text-sm text-red-600 hover:text-red-800"
                        onClick={handleBatchDelete}
                    >
                        <Trash2 className="w-4 h-4"/>
                        {t("template_lib.delete")}
                    </button>
                </div>
            )}

            {/* 首选项提示 */}
            {prefMode && (
                <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-700">
                    {t("template_lib.pref_hint")}
                </div>
            )}

            {/* 加载中 */}
            {loading ? (
                <div className="flex items-center justify-center h-40">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500"/>
                </div>
            ) : templates.length === 0 ? (
                <div className="text-center py-16 text-gray-400">
                    <FileSpreadsheet className="w-12 h-12 mx-auto mb-3 text-gray-300"/>
                    <p>{t("template_lib.empty")}</p>
                    <button
                        className="mt-4 px-4 py-2 bg-blue-500 text-white rounded-lg text-sm hover:bg-blue-600"
                        onClick={() => fileInputRef.current?.click()}
                    >
                        {t("template_lib.import_first")}
                    </button>
                </div>
            ) : categoryView ? (
                renderCategoryView()
            ) : (
                renderFlatView()
            )}

            {/* 隐藏的文件输入 */}
            <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".xlsx"
                multiple
                onChange={(e) => handleImport(e.target.files)}
            />

            {/* 预览弹窗 */}
            {renderPreviewModal()}
        </div>
    );
}
