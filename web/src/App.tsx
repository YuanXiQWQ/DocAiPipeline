import React, {useState, useCallback, useRef, useEffect} from "react";
import {Routes, Route, Link, useLocation, useNavigate} from "react-router-dom";
import {
    Upload,
    FileText,
    CheckCircle,
    AlertCircle,
    Download,
    Loader2,
    ScanLine,
    Truck,
    Package,
    Scissors,
    ClipboardList,
    Settings,
    Clock,
    BarChart3,
    TreePine,
    Home,
} from "lucide-react";
import {useT} from "./i18n";
import SettingsPanel from "./SettingsPanel";
import HistoryPanel from "./HistoryPanel";
import DashboardPanel from "./DashboardPanel";
import {
    classifyDocument,
    processDocument,
    fillExcel,
    healthCheck,
    getSettings,
    extractErrorMessage,
    DOC_TYPE_KEYS,
    type ClassifyResult,
    type ProcessResult,
    type FillResult,
} from "./api";

/* 文档类型图标映射 */
const DOC_ICONS: Record<string, React.ReactNode> = {
    customs: <Truck className="w-5 h-5"/>,
    log_measurement: <TreePine className="w-5 h-5"/>,
    log_output: <ClipboardList className="w-5 h-5"/>,
    soak_pool: <Package className="w-5 h-5"/>,
    slicing: <Scissors className="w-5 h-5"/>,
    packing: <Package className="w-5 h-5"/>,
};

type Step = "upload" | "processing" | "review" | "filling" | "done";

export default function App() {
    const t = useT();
    const location = useLocation();
    const navigate = useNavigate();
    const [step, setStep] = useState<Step>("upload");
    const [file, setFile] = useState<File | null>(null);
    const [docType, setDocType] = useState("auto");
    const [result, setResult] = useState<ProcessResult | null>(null);
    const [fillResult, setFillResult] = useState<FillResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [templateFile, setTemplateFile] = useState<File | null>(null);
    const [classifyInfo, setClassifyInfo] = useState<ClassifyResult | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const [backendOk, setBackendOk] = useState<boolean | null>(null);
    const [dragging, setDragging] = useState(false);
    const [preview, setPreview] = useState<string | null>(null);
    const [needsSetup, setNeedsSetup] = useState(false);

    useEffect(() => {
        healthCheck()
            .then(() => {
                setBackendOk(true);
                return getSettings();
            })
            .then((res) => {
                if (!res.settings.openai_api_key_set) {
                    setNeedsSetup(true);
                    navigate("/settings");
                }
            })
            .catch(() => setBackendOk(false));
    }, []);

    const selectFile = useCallback((f: File) => {
        setFile(f);
        if (f.type.startsWith("image/")) {
            setPreview(URL.createObjectURL(f));
        } else {
            setPreview(null);
        }
    }, []);

    const handleFileSelect = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            const f = e.target.files?.[0];
            if (f) selectFile(f);
        },
        [selectFile]
    );

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setDragging(false);
        const f = e.dataTransfer.files[0];
        if (f) selectFile(f);
    }, [selectFile]);

    const handleProcess = useCallback(async () => {
        if (!file) return;
        setStep("processing");
        setError(null);
        setClassifyInfo(null);
        try {
            // 自动模式下先调分类接口，显示分类结果
            if (docType === "auto") {
                const cls = await classifyDocument(file);
                setClassifyInfo(cls);
            }
            const res = await processDocument(file, docType);
            setResult(res);
            setStep("review");
        } catch (err: unknown) {
            setError(extractErrorMessage(err));
            setStep("upload");
        }
    }, [file, docType]);

    const handleFill = useCallback(async () => {
        if (!result) return;
        setStep("filling");
        setError(null);
        try {
            const res = await fillExcel(
                result.doc_type,
                result.results,
                templateFile || undefined
            );
            setFillResult(res);
            setStep("done");
        } catch (err: unknown) {
            setError(extractErrorMessage(err));
            setStep("review");
        }
    }, [result, templateFile]);

    const handleReset = useCallback(() => {
        setStep("upload");
        setFile(null);
        setResult(null);
        setFillResult(null);
        setError(null);
        setTemplateFile(null);
        setClassifyInfo(null);
        setPreview(null);
    }, []);

    /* 导航链接配置 */
    const navItems = [
        {to: "/", icon: <Home className="w-5 h-5"/>, label: t("step.upload")},
        {to: "/dashboard", icon: <BarChart3 className="w-5 h-5"/>, label: t("nav.dashboard")},
        {to: "/history", icon: <Clock className="w-5 h-5"/>, label: t("nav.history")},
        {to: "/settings", icon: <Settings className="w-5 h-5"/>, label: t("nav.settings")},
    ];

    const handleLoadFromHistory = useCallback((detail: { doc_type: string; filename: string; pages: number; results: Record<string, unknown>[]; warnings: string[] }) => {
        setResult({
            doc_type: detail.doc_type,
            filename: detail.filename,
            pages: detail.pages,
            results: detail.results,
            warnings: detail.warnings,
        });
        setStep("review");
        navigate("/");
    }, [navigate]);

    const handleSettingsChange = useCallback(() => {
        getSettings()
            .then((res) => setNeedsSetup(!res.settings.openai_api_key_set))
            .catch(() => {});
    }, []);

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
            {/* 顶栏 */}
            <header className="bg-white/80 backdrop-blur border-b border-slate-200 sticky top-0 z-10">
                <div className="max-w-5xl mx-auto px-6 py-3 flex items-center justify-between">
                    <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
                        <ScanLine className="w-7 h-7 text-emerald-600"/>
                        <h1 className="text-lg font-semibold text-slate-800">
                            {t("app.title")}
                        </h1>
                    </Link>
                    <div className="flex items-center gap-1">
                        <p className="text-sm text-slate-500 hidden sm:block mr-2">
                            {t("app.subtitle")}
                        </p>
                        {backendOk !== null && (
                            <span
                                className={`w-2 h-2 rounded-full mr-2 ${
                                    backendOk ? "bg-emerald-500" : "bg-red-400"
                                }`}
                                title={backendOk ? t("error.backend_online") : t("error.backend_offline")}
                            />
                        )}
                        {navItems.map((item) => (
                            <Link
                                key={item.to}
                                to={item.to}
                                className={`p-2 rounded-lg transition-colors flex items-center gap-1.5 text-sm ${
                                    location.pathname === item.to
                                        ? "bg-blue-50 text-blue-600"
                                        : "hover:bg-slate-100 text-slate-500"
                                }`}
                                title={item.label}
                            >
                                {item.icon}
                                <span className="hidden md:inline">{item.label}</span>
                            </Link>
                        ))}
                    </div>
                </div>
            </header>

            <main className="max-w-5xl mx-auto px-6 py-10">
                <Routes>
                    <Route path="/settings" element={
                        <SettingsPanel onSettingsChange={handleSettingsChange}/>
                    }/>
                    <Route path="/history" element={
                        <HistoryPanel onLoadResult={handleLoadFromHistory}/>
                    }/>
                    <Route path="/dashboard" element={
                        <DashboardPanel/>
                    }/>
                    <Route path="*" element={
                        <ProcessingFlow
                            t={t}
                            step={step}
                            setStep={setStep}
                            file={file}
                            setFile={setFile}
                            docType={docType}
                            setDocType={setDocType}
                            result={result}
                            setResult={setResult}
                            fillResult={fillResult}
                            setFillResult={setFillResult}
                            error={error}
                            setError={setError}
                            templateFile={templateFile}
                            setTemplateFile={setTemplateFile}
                            classifyInfo={classifyInfo}
                            setClassifyInfo={setClassifyInfo}
                            inputRef={inputRef}
                            dragging={dragging}
                            setDragging={setDragging}
                            preview={preview}
                            setPreview={setPreview}
                            needsSetup={needsSetup}
                            selectFile={selectFile}
                            handleFileSelect={handleFileSelect}
                            handleDrop={handleDrop}
                            handleProcess={handleProcess}
                            handleFill={handleFill}
                            handleReset={handleReset}
                        />
                    }/>
                </Routes>
            </main>

            {/* 底栏 */}
            <footer className="text-center text-sm text-slate-400 py-6 mt-auto">
                {t("footer.powered")} DocAI Pipeline &copy; {new Date().getFullYear()}
            </footer>
        </div>
    );
}

/* 文档处理流程组件（首页） */
function ProcessingFlow({
    t, step, setStep, file, setFile, docType, setDocType,
    result, setResult, fillResult, setFillResult, error, setError,
    templateFile, setTemplateFile, classifyInfo, setClassifyInfo,
    inputRef, dragging, setDragging, preview, setPreview,
    needsSetup, selectFile, handleFileSelect, handleDrop,
    handleProcess, handleFill, handleReset,
}: {
    t: (key: string) => string;
    step: Step;
    setStep: (s: Step) => void;
    file: File | null;
    setFile: (f: File | null) => void;
    docType: string;
    setDocType: (d: string) => void;
    result: ProcessResult | null;
    setResult: (r: ProcessResult | null) => void;
    fillResult: FillResult | null;
    setFillResult: (r: FillResult | null) => void;
    error: string | null;
    setError: (e: string | null) => void;
    templateFile: File | null;
    setTemplateFile: (f: File | null) => void;
    classifyInfo: ClassifyResult | null;
    setClassifyInfo: (c: ClassifyResult | null) => void;
    inputRef: React.RefObject<HTMLInputElement | null>;
    dragging: boolean;
    setDragging: (d: boolean) => void;
    preview: string | null;
    setPreview: (p: string | null) => void;
    needsSetup: boolean;
    selectFile: (f: File) => void;
    handleFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
    handleDrop: (e: React.DragEvent) => void;
    handleProcess: () => void;
    handleFill: () => void;
    handleReset: () => void;
}) {
    return (
        <>
            {/* 首次运行引导横幅 */}
            {needsSetup && step === "upload" && (
                <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5"/>
                    <div className="flex-1">
                        <p className="text-amber-800 font-medium">{t("setup.welcome")}</p>
                        <p className="text-amber-600 text-sm mt-1">
                            {t("setup.hint")}
                        </p>
                    </div>
                    <Link
                        to="/settings"
                        className="px-4 py-1.5 bg-amber-600 text-white rounded-lg hover:bg-amber-700 transition-colors text-sm font-medium shrink-0"
                    >
                        {t("setup.go_settings")}
                    </Link>
                </div>
            )}

            {/* 步骤指示器 */}
            <div className="flex items-center justify-center gap-2 mb-10">
                {(
                    [
                        ["upload", t("step.upload")],
                        ["processing", t("step.processing")],
                        ["review", t("step.review")],
                        ["done", t("step.done")],
                    ] as const
                ).map(([s, label], i) => {
                    const active =
                        s === step || (s === "processing" && step === "filling");
                    const completed =
                        (s === "upload" && step !== "upload") ||
                        (s === "processing" &&
                            ["review", "filling", "done"].includes(step)) ||
                        (s === "review" && ["filling", "done"].includes(step));
                    return (
                        <div key={s} className="flex items-center gap-2">
                            {i > 0 && (
                                <div
                                    className={`w-8 h-px ${completed ? "bg-emerald-400" : "bg-slate-300"}`}
                                />
                            )}
                            <div
                                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                                    active
                                        ? "bg-blue-600 text-white"
                                        : completed
                                            ? "bg-emerald-500 text-white"
                                            : "bg-slate-200 text-slate-500"
                                }`}
                            >
                                {completed ? (
                                    <CheckCircle className="w-4 h-4"/>
                                ) : (
                                    i + 1
                                )}
                            </div>
                            <span
                                className={`text-sm ${active ? "text-blue-700 font-medium" : "text-slate-500"}`}
                            >
                                {label}
                            </span>
                        </div>
                    );
                })}
            </div>

            {/* 错误提示 */}
            {error && (
                <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5"/>
                    <div>
                        <p className="text-red-800 font-medium">{t("error.processing")}</p>
                        <p className="text-red-600 text-sm mt-1">{error}</p>
                    </div>
                </div>
            )}

            {/* ===== 步骤 1: 上传 ===== */}
            {step === "upload" && (
                <div className="space-y-6">
                    {/* 文档类型选择 */}
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                        <h2 className="text-base font-semibold text-slate-700 mb-4">
                            {t("upload.select_type")}
                        </h2>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            {Object.entries(DOC_TYPE_KEYS).map(([key, i18nKey]) => (
                                <button
                                    key={key}
                                    onClick={() => setDocType(key)}
                                    className={`p-3 rounded-xl border text-left transition-all text-sm ${
                                        docType === key
                                            ? "border-blue-500 bg-blue-50 text-blue-700 shadow-sm"
                                            : "border-slate-200 hover:border-slate-300 text-slate-600"
                                    }`}
                                >
                                    <div className="flex items-center gap-2">
                                        {DOC_ICONS[key] || <FileText className="w-5 h-5"/>}
                                        <span className="font-medium">{t(i18nKey)}</span>
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* 文件上传区 */}
                    <div
                        className={`bg-white rounded-2xl shadow-sm border-2 border-dashed transition-colors p-12 text-center cursor-pointer ${
                            dragging
                                ? "border-blue-500 bg-blue-50"
                                : "border-slate-300 hover:border-blue-400"
                        }`}
                        onClick={() => inputRef.current?.click()}
                        onDragOver={(e) => e.preventDefault()}
                        onDragEnter={() => setDragging(true)}
                        onDragLeave={() => setDragging(false)}
                        onDrop={handleDrop}
                    >
                        <input
                            ref={inputRef}
                            type="file"
                            accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif"
                            className="hidden"
                            onChange={handleFileSelect}
                        />
                        <Upload
                            className={`w-12 h-12 mx-auto mb-4 ${dragging ? "text-blue-500" : "text-slate-400"}`}/>
                        <p className="text-slate-600 font-medium">
                            {t("upload.hint")}
                        </p>
                        <p className="text-sm text-slate-400 mt-2">
                            {t("upload.supported")}
                        </p>
                    </div>

                    {/* 已选文件 */}
                    {file && (
                        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <FileText className="w-8 h-8 text-blue-500"/>
                                    <div>
                                        <p className="font-medium text-slate-800">{file.name}</p>
                                        <p className="text-sm text-slate-400">
                                            {(file.size / 1024).toFixed(1)} KB
                                        </p>
                                    </div>
                                </div>
                                <button
                                    onClick={handleProcess}
                                    className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-medium flex items-center gap-2"
                                >
                                    <Upload className="w-4 h-4"/>
                                    {t("upload.start")}
                                </button>
                            </div>
                            {/* 图片预览 */}
                            {preview && (
                                <div className="mt-4 border border-slate-200 rounded-xl overflow-hidden">
                                    <img
                                        src={preview}
                                        alt="预览"
                                        className="max-h-64 mx-auto object-contain"
                                    />
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* ===== 步骤 2: 处理中 ===== */}
            {(step === "processing" || step === "filling") && (
                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-16 text-center">
                    <Loader2 className="w-12 h-12 text-blue-500 mx-auto mb-4 animate-spin"/>
                    <p className="text-lg text-slate-700 font-medium">
                        {step === "processing" ? t("processing.recognizing") : t("processing.filling")}
                    </p>
                    <p className="text-sm text-slate-400 mt-2">
                        {t("processing.hint")}
                    </p>
                </div>
            )}

            {/* ===== 步骤 3: 复核 ===== */}
            {step === "review" && result && (
                <div className="space-y-6">
                    {/* 自动分类结果 */}
                    {classifyInfo && (
                        <div className="bg-blue-50 border border-blue-200 rounded-2xl p-4 flex items-center gap-3">
                            {DOC_ICONS[classifyInfo.doc_type] || <FileText className="w-5 h-5"/>}
                            <div className="text-left">
                                <p className="text-sm font-medium text-blue-800">
                                    {t("review.classify")}: {DOC_TYPE_KEYS[classifyInfo.doc_type] ? t(DOC_TYPE_KEYS[classifyInfo.doc_type]) : classifyInfo.doc_type}
                                    <span className="ml-2 text-xs text-blue-500">({classifyInfo.confidence})</span>
                                </p>
                                <p className="text-xs text-blue-600">{classifyInfo.description}</p>
                            </div>
                        </div>
                    )}

                    {/* 识别概览 */}
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-base font-semibold text-slate-700">
                                {t("review.title")}
                            </h2>
                            <span className="px-3 py-1 bg-emerald-100 text-emerald-700 rounded-full text-sm font-medium flex items-center gap-1">
                                {DOC_ICONS[result.doc_type]}
                                {DOC_TYPE_KEYS[result.doc_type] ? t(DOC_TYPE_KEYS[result.doc_type]) : result.doc_type}
                            </span>
                        </div>
                        <div className="grid grid-cols-3 gap-4 text-center">
                            <div className="bg-slate-50 rounded-xl p-4">
                                <p className="text-2xl font-bold text-slate-800">{result.pages}</p>
                                <p className="text-sm text-slate-500">{t("review.pages")}</p>
                            </div>
                            <div className="bg-slate-50 rounded-xl p-4">
                                <p className="text-2xl font-bold text-slate-800">{result.results.length}</p>
                                <p className="text-sm text-slate-500">{t("review.records")}</p>
                            </div>
                            <div className="bg-slate-50 rounded-xl p-4">
                                <p className="text-2xl font-bold text-slate-800">{result.warnings.length}</p>
                                <p className="text-sm text-slate-500">{t("review.warnings")}</p>
                            </div>
                        </div>
                    </div>

                    {/* 警告列表 */}
                    {result.warnings.length > 0 && (
                        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
                            <h3 className="font-medium text-amber-800 mb-2 flex items-center gap-2">
                                <AlertCircle className="w-4 h-4"/>
                                {t("review.warnings")}
                            </h3>
                            <ul className="space-y-1">
                                {result.warnings.map((w, i) => (
                                    <li key={i} className="text-sm text-amber-700">• {w}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {/* 数据预览 */}
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                        <h3 className="font-medium text-slate-700 mb-3">{t("review.data_preview")}</h3>
                        <div className="max-h-[48rem] overflow-auto">
                            {result.results.map((rec, ri) => {
                                const entries = (rec.entries ?? rec.fields ?? []) as Record<string, unknown>[];
                                const cropFile = rec.crop_image_path as string | undefined;
                                const cropUrl = cropFile
                                    ? `/api/crop/${encodeURIComponent(typeof cropFile === "string" && cropFile.includes("/") ? cropFile.split("/").pop()! : cropFile)}`
                                    : null;

                                if (!Array.isArray(entries) || entries.length === 0) {
                                    return (
                                        <details key={ri} className="mb-3">
                                            <summary className="text-sm font-medium text-slate-600 cursor-pointer">
                                                {t("review.record")} {ri + 1}
                                            </summary>
                                            {cropUrl && (
                                                <div className="mt-2 mb-2 border border-slate-200 rounded-lg overflow-hidden max-h-64">
                                                    <img src={cropUrl} alt={`${t("review.record")} ${ri + 1}`} className="w-full object-contain max-h-64"/>
                                                </div>
                                            )}
                                            <pre className="text-xs bg-slate-50 rounded-lg p-3 mt-1 whitespace-pre-wrap">
                                                {JSON.stringify(rec, null, 2).slice(0, 2000)}
                                            </pre>
                                        </details>
                                    );
                                }
                                const cols = Object.keys(entries[0]).filter(
                                    (k) => k !== "needs_review" && k !== "review_reason"
                                );
                                return (
                                    <details key={ri} open={result.results.length === 1} className="mb-3">
                                        <summary className="text-sm font-medium text-slate-600 cursor-pointer">
                                            {t("review.record")} {ri + 1} — {entries.length} {t("review.rows")}
                                        </summary>
                                        {cropUrl && (
                                            <div className="mt-2 mb-3 border border-slate-200 rounded-lg overflow-hidden">
                                                <p className="text-xs text-slate-500 bg-slate-50 px-3 py-1 border-b border-slate-200">
                                                    {t("review.crop_hint")}
                                                </p>
                                                <a href={cropUrl} target="_blank" rel="noopener noreferrer">
                                                    <img src={cropUrl} alt={`${t("review.record")} ${ri + 1}`} className="w-full object-contain max-h-72 cursor-zoom-in"/>
                                                </a>
                                            </div>
                                        )}
                                        <div className="overflow-x-auto mt-2">
                                            <table className="min-w-full text-xs border-collapse">
                                                <thead>
                                                <tr className="bg-slate-100">
                                                    {cols.map((c) => (
                                                        <th key={c} className="px-2 py-1 border border-slate-200 text-left font-medium text-slate-600 whitespace-nowrap">{c}</th>
                                                    ))}
                                                </tr>
                                                </thead>
                                                <tbody>
                                                {entries.slice(0, 50).map((row, rIdx) => (
                                                    <tr key={rIdx} className={rIdx % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                                                        {cols.map((c) => (
                                                            <td key={c} className="px-2 py-1 border border-slate-200 text-slate-700 whitespace-nowrap">{String(row[c] ?? "")}</td>
                                                        ))}
                                                    </tr>
                                                ))}
                                                </tbody>
                                            </table>
                                            {entries.length > 50 && (
                                                <p className="text-xs text-slate-400 mt-1">{t("review.more_rows").replace("{n}", String(entries.length - 50))}</p>
                                            )}
                                        </div>
                                    </details>
                                );
                            })}
                        </div>
                    </div>

                    {/* Excel 模板上传 */}
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                        <h3 className="font-medium text-slate-700 mb-3">{t("upload.template")}</h3>
                        <p className="text-sm text-slate-500 mb-3">{t("upload.template_hint")}</p>
                        <input
                            type="file"
                            accept=".xlsx"
                            onChange={(e) => setTemplateFile(e.target.files?.[0] || null)}
                            className="text-sm text-slate-600"
                        />
                    </div>

                    {/* 操作按钮 */}
                    <div className="flex gap-4 justify-end">
                        <button
                            onClick={handleReset}
                            className="px-6 py-2.5 border border-slate-300 text-slate-600 rounded-xl hover:bg-slate-50 transition-colors"
                        >
                            {t("upload.reupload")}
                        </button>
                        <button
                            onClick={handleFill}
                            className="px-6 py-2.5 bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 transition-colors font-medium flex items-center gap-2"
                        >
                            <Download className="w-4 h-4"/>
                            {t("review.fill")}
                        </button>
                    </div>
                </div>
            )}

            {/* ===== 步骤 4: 完成 ===== */}
            {step === "done" && fillResult && (
                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-12 text-center">
                    <CheckCircle className="w-16 h-16 text-emerald-500 mx-auto mb-6"/>
                    <h2 className="text-xl font-semibold text-slate-800 mb-2">{t("done.title")}</h2>
                    <p className="text-slate-500 mb-6">
                        {t("done.rows_written").replace("{n}", String(fillResult.rows_written))}
                    </p>
                    <div className="flex gap-4 justify-center">
                        <a
                            href={fillResult.download_url}
                            download
                            className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-medium inline-flex items-center gap-2"
                        >
                            <Download className="w-4 h-4"/>
                            {t("done.download")}
                        </a>
                        <button
                            onClick={handleReset}
                            className="px-6 py-2.5 border border-slate-300 text-slate-600 rounded-xl hover:bg-slate-50 transition-colors"
                        >
                            {t("done.new")}
                        </button>
                    </div>
                </div>
            )}
        </>
    );
}
