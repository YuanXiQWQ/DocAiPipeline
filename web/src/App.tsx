import React, {useCallback, useEffect, useRef, useState} from "react";
import {Link, Route, Routes, useLocation, useNavigate} from "react-router-dom";
import {
    AlertCircle,
    BarChart3,
    CheckCircle,
    ClipboardList,
    Clock,
    Download,
    FileText,
    Home,
    Loader2,
    Package,
    ScanLine,
    Scissors,
    Settings,
    TreePine,
    Truck,
    Upload,
} from "lucide-react";
import {useT} from "./i18n";
import SettingsPanel from "./SettingsPanel";
import HistoryPanel from "./HistoryPanel";
import DashboardPanel from "./DashboardPanel";
import {
    type BatchErrorEvent,
    type BatchProgressEvent,
    type BatchResultEvent,
    classifyDocument,
    type ClassifyResult,
    DOC_TYPE_KEYS,
    extractErrorMessage,
    fillExcel,
    type FillResult,
    getSettings,
    healthCheck,
    processBatch,
    processDocument,
    type ProcessResult,
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

/* UI 视图状态（与后台处理解耦） */
type View = "upload" | "review" | "filling" | "done";

/* 每个文件的处理状态 */
type FileStatus = "waiting" | "processing" | "success" | "error";

interface FileEntry {
    file: File;
    status: FileStatus;
    error?: string;
    result?: ProcessResult;
    classifyInfo?: ClassifyResult;
}

export default function App() {
    const t = useT();
    const location = useLocation();
    const navigate = useNavigate();

    /* UI 视图（可自由切换，不影响后台处理） */
    const [view, setView] = useState<View>("upload");

    /* 文件列表（贯穿整个会话） */
    const [files, setFiles] = useState<FileEntry[]>([]);
    const [selectedFileIndex, setSelectedFileIndex] = useState<number>(-1);
    const [docType, setDocType] = useState("auto");

    /* 填充相关（对选中文件操作） */
    const [fillResult, setFillResult] = useState<FillResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [templateFile, setTemplateFile] = useState<File | null>(null);

    const inputRef = useRef<HTMLInputElement>(null);
    const [backendOk, setBackendOk] = useState<boolean | null>(null);
    const [dragging, setDragging] = useState(false);
    const [preview, setPreview] = useState<string | null>(null);
    const [needsSetup, setNeedsSetup] = useState(false);
    const batchAbortRef = useRef<{ abort: () => void } | null>(null);

    /* 派生状态 */
    const isProcessing = files.some(f => f.status === "processing" || f.status === "waiting" && files.some(g => g.status === "processing"));
    const selectedFile = selectedFileIndex >= 0 ? files[selectedFileIndex] : null;
    const selectedResult = selectedFile?.result ?? null;

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

    const addFiles = useCallback((newFiles: FileList | File[]) => {
        const arr = Array.from(newFiles);
        setFiles(prev => [
            ...prev,
            ...arr.map(f => ({file: f, status: "waiting" as FileStatus})),
        ]);
        // 预览第一张图片
        const first = arr[0];
        if (first && first.type.startsWith("image/")) {
            setPreview(URL.createObjectURL(first));
        }
    }, []);

    const removeFile = useCallback((index: number) => {
        setFiles(prev => prev.filter((_, i) => i !== index));
    }, []);

    const handleFileSelect = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            if (e.target.files?.length) addFiles(e.target.files);
        },
        [addFiles]
    );

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setDragging(false);
        if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
    }, [addFiles]);

    /* 开始处理：只处理 waiting 状态的文件，不影响已完成的 */
    const handleProcess = useCallback(() => {
        const pendingIndices = files
            .map((f, i) => f.status === "waiting" ? i : -1)
            .filter(i => i >= 0);
        if (pendingIndices.length === 0) return;

        setError(null);

        // 重置待处理文件状态
        setFiles(prev => prev.map((f, i) =>
            pendingIndices.includes(i)
                ? {...f, status: "waiting" as FileStatus, error: undefined, result: undefined, classifyInfo: undefined}
                : f
        ));

        const rawFiles = pendingIndices.map(i => files[i].file);

        // 单文件走原有路径
        if (rawFiles.length === 1) {
            const idx = pendingIndices[0];
            (async () => {
                setFiles(prev => prev.map((f, i) => i === idx ? {...f, status: "processing"} : f));
                try {
                    let cls: ClassifyResult | undefined;
                    if (docType === "auto") {
                        cls = await classifyDocument(rawFiles[0]);
                    }
                    const res = await processDocument(rawFiles[0], docType);
                    setFiles(prev => prev.map((f, i) => i === idx ? {
                        ...f,
                        status: "success",
                        result: res,
                        classifyInfo: cls
                    } : f));
                    // 自动跳转到该文件的复核视图
                    setSelectedFileIndex(idx);
                    setView("review");
                } catch (err: unknown) {
                    setFiles(prev => prev.map((f, i) => i === idx ? {
                        ...f,
                        status: "error",
                        error: extractErrorMessage(err)
                    } : f));
                }
            })();
            return;
        }

        // 多文件走 SSE 批量处理
        batchAbortRef.current = processBatch(rawFiles, docType, {
            onProgress: (e: BatchProgressEvent) => {
                const fileIdx = pendingIndices[e.index];
                setFiles(prev => prev.map((f, i) => i === fileIdx ? {...f, status: "processing"} : f));
            },
            onResult: (e: BatchResultEvent) => {
                const fileIdx = pendingIndices[e.index];
                setFiles(prev => prev.map((f, i) => i === fileIdx ? {...f, status: "success", result: e.data} : f));
            },
            onError: (e: BatchErrorEvent) => {
                const fileIdx = pendingIndices[e.index];
                setFiles(prev => prev.map((f, i) => i === fileIdx ? {...f, status: "error", error: e.error} : f));
            },
            onDone: () => {
                // 如果用户还在 upload 视图，自动跳转到第一个成功文件的复核
                setFiles(prev => {
                    const firstSuccessIdx = prev.findIndex(f => f.status === "success" && f.result);
                    if (firstSuccessIdx >= 0) {
                        setSelectedFileIndex(firstSuccessIdx);
                        setView("review");
                    }
                    return prev;
                });
            },
        });
    }, [files, docType]);

    const handleFill = useCallback(async () => {
        if (!selectedResult) return;
        setView("filling");
        setError(null);
        try {
            const res = await fillExcel(
                selectedResult.doc_type,
                selectedResult.results,
                templateFile || undefined
            );
            setFillResult(res);
            setView("done");
        } catch (err: unknown) {
            setError(extractErrorMessage(err));
            setView("review");
        }
    }, [selectedResult, templateFile]);

    /* 回到主页（不中断处理，不清状态） */
    const handleGoHome = useCallback(() => {
        setView("upload");
        setError(null);
    }, []);

    /* 彻底重置 */
    const handleReset = useCallback(() => {
        batchAbortRef.current?.abort();
        batchAbortRef.current = null;
        setView("upload");
        setFiles([]);
        setSelectedFileIndex(-1);
        setFillResult(null);
        setError(null);
        setTemplateFile(null);
        setPreview(null);
    }, []);

    /* 点击文件列表中的文件查看结果 */
    const handleSelectFile = useCallback((index: number) => {
        setSelectedFileIndex(index);
        const entry = files[index];
        if (entry?.status === "success" && entry.result) {
            setView("review");
            setFillResult(null);
            setError(null);
        }
    }, [files]);

    /* 导航链接配置 */
    const navItems = [
        {to: "/", icon: <Home className="w-5 h-5"/>, label: t("step.upload")},
        {to: "/dashboard", icon: <BarChart3 className="w-5 h-5"/>, label: t("nav.dashboard")},
        {to: "/history", icon: <Clock className="w-5 h-5"/>, label: t("nav.history")},
        {to: "/settings", icon: <Settings className="w-5 h-5"/>, label: t("nav.settings")},
    ];

    const handleLoadFromHistory = useCallback((detail: {
        doc_type: string;
        filename: string;
        pages: number;
        results: Record<string, unknown>[];
        warnings: string[]
    }) => {
        const fakeResult: ProcessResult = {
            doc_type: detail.doc_type,
            filename: detail.filename,
            pages: detail.pages,
            results: detail.results,
            warnings: detail.warnings,
        };
        // 将历史记录作为虚拟文件插入列表
        const fakeEntry: FileEntry = {
            file: new File([], detail.filename),
            status: "success",
            result: fakeResult,
        };
        setFiles(prev => {
            const newFiles = [...prev, fakeEntry];
            setSelectedFileIndex(newFiles.length - 1);
            return newFiles;
        });
        setView("review");
        navigate("/");
    }, [navigate]);

    const handleSettingsChange = useCallback(() => {
        getSettings()
            .then((res) => setNeedsSetup(!res.settings.openai_api_key_set))
            .catch(() => {
            });
    }, []);

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
            {/* 顶栏 */}
            <header className="bg-white/80 backdrop-blur border-b border-slate-200 sticky top-0 z-10">
                <div className="max-w-5xl mx-auto px-6 py-3 flex items-center justify-between">
                    <button onClick={() => {
                        handleGoHome();
                        navigate("/");
                    }} className="flex items-center gap-3 hover:opacity-80 transition-opacity">
                        <ScanLine className="w-7 h-7 text-emerald-600"/>
                        <h1 className="text-lg font-semibold text-slate-800">
                            {t("app.title")}
                        </h1>
                    </button>
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
                            view={view}
                            files={files}
                            selectedFileIndex={selectedFileIndex}
                            selectedResult={selectedResult}
                            isProcessing={isProcessing}
                            removeFile={removeFile}
                            handleSelectFile={handleSelectFile}
                            docType={docType}
                            setDocType={setDocType}
                            fillResult={fillResult}
                            error={error}
                            setTemplateFile={setTemplateFile}
                            inputRef={inputRef}
                            dragging={dragging}
                            setDragging={setDragging}
                            preview={preview}
                            needsSetup={needsSetup}
                            handleFileSelect={handleFileSelect}
                            handleDrop={handleDrop}
                            handleProcess={handleProcess}
                            handleFill={handleFill}
                            handleReset={handleReset}
                            handleGoHome={handleGoHome}
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
                            t, view, files, selectedFileIndex, selectedResult, isProcessing,
                            removeFile, handleSelectFile, docType, setDocType,
                            fillResult, error, setTemplateFile,
                            inputRef, dragging, setDragging, preview,
                            needsSetup, handleFileSelect, handleDrop,
                            handleProcess, handleFill, handleReset, handleGoHome,
                        }: {
    t: (key: string) => string;
    view: View;
    files: FileEntry[];
    selectedFileIndex: number;
    selectedResult: ProcessResult | null;
    isProcessing: boolean;
    removeFile: (index: number) => void;
    handleSelectFile: (index: number) => void;
    docType: string;
    setDocType: (d: string) => void;
    fillResult: FillResult | null;
    error: string | null;
    setTemplateFile: (f: File | null) => void;
    inputRef: React.RefObject<HTMLInputElement | null>;
    dragging: boolean;
    setDragging: (d: boolean) => void;
    preview: string | null;
    needsSetup: boolean;
    handleFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
    handleDrop: (e: React.DragEvent) => void;
    handleProcess: () => void;
    handleFill: () => void;
    handleReset: () => void;
    handleGoHome: () => void;
}) {
    const statusColor: Record<FileStatus, string> = {
        waiting: "bg-slate-300",
        processing: "bg-blue-500 animate-pulse",
        success: "bg-emerald-500",
        error: "bg-red-500",
    };
    const statusLabel: Record<FileStatus, string> = {
        waiting: t("upload.file_waiting"),
        processing: t("upload.file_processing"),
        success: t("upload.file_success"),
        error: t("upload.file_error"),
    };

    const selectedFile = selectedFileIndex >= 0 ? files[selectedFileIndex] : null;

    /* 步骤指示器数据 */
    const stepDef: [string, string][] = [
        ["upload", t("step.upload")],
        ["processing", t("step.processing")],
        ["review", t("step.review")],
        ["done", t("step.done")],
    ];
    const successCount = files.filter(f => f.status === "success").length;
    const hasWaiting = files.some(f => f.status === "waiting");

    return (
        <>
            {/* 首次运行引导横幅 */}
            {needsSetup && view === "upload" && (
                <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5"/>
                    <div className="flex-1">
                        <p className="text-amber-800 font-medium">{t("setup.welcome")}</p>
                        <p className="text-amber-600 text-sm mt-1">{t("setup.hint")}</p>
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
                {stepDef.map(([s, label], i) => {
                    const active =
                        (s === "upload" && view === "upload") ||
                        (s === "processing" && (isProcessing || view === "filling")) ||
                        (s === "review" && view === "review") ||
                        (s === "done" && view === "done");
                    const completed =
                        (s === "upload" && view !== "upload") ||
                        (s === "processing" && !isProcessing && ["review", "done"].includes(view) && successCount > 0) ||
                        (s === "review" && view === "done");
                    return (
                        <div key={s} className="flex items-center gap-2">
                            {i > 0 && (
                                <div className={`w-8 h-px ${completed ? "bg-emerald-400" : "bg-slate-300"}`}/>
                            )}
                            <div
                                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                                    active ? "bg-blue-600 text-white"
                                        : completed ? "bg-emerald-500 text-white"
                                            : "bg-slate-200 text-slate-500"
                                }`}>
                                {completed ? <CheckCircle className="w-4 h-4"/> : i + 1}
                            </div>
                            <span className={`text-sm ${active ? "text-blue-700 font-medium" : "text-slate-500"}`}>
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

            {/* ===== 主页视图：上传 + 文件列表 ===== */}
            {view === "upload" && (
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
                            dragging ? "border-blue-500 bg-blue-50" : "border-slate-300 hover:border-blue-400"
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
                            multiple
                            className="hidden"
                            onChange={handleFileSelect}
                        />
                        <Upload className={`w-12 h-12 mx-auto mb-4 ${dragging ? "text-blue-500" : "text-slate-400"}`}/>
                        <p className="text-slate-600 font-medium">{t("upload.hint")}</p>
                        <p className="text-sm text-slate-400 mt-2">{t("upload.supported")}</p>
                    </div>

                    {/* 文件列表 */}
                    {files.length > 0 && (
                        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-3">
                            <div className="flex items-center justify-between mb-2">
                                <p className="text-sm font-medium text-slate-600">
                                    {t("upload.files_selected").replace("{n}", String(files.length))}
                                    {isProcessing && (
                                        <span className="ml-2 inline-flex items-center gap-1 text-blue-600">
                                            <Loader2 className="w-3.5 h-3.5 animate-spin"/>
                                            {t("upload.file_processing")}
                                        </span>
                                    )}
                                </p>
                                <div className="flex gap-2">
                                    {hasWaiting && (
                                        <button
                                            onClick={handleProcess}
                                            disabled={isProcessing}
                                            className="px-5 py-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 transition-colors font-medium flex items-center gap-2 text-sm"
                                        >
                                            <Upload className="w-4 h-4"/>
                                            {t("upload.start")}
                                        </button>
                                    )}
                                    {files.length > 0 && !isProcessing && (
                                        <button
                                            onClick={handleReset}
                                            className="px-4 py-2 border border-slate-300 text-slate-500 rounded-xl hover:bg-slate-50 transition-colors text-sm"
                                        >
                                            {t("upload.reupload")}
                                        </button>
                                    )}
                                </div>
                            </div>
                            <div className="space-y-1 max-h-96 overflow-auto">
                                {files.map((entry, idx) => (
                                    <div
                                        key={idx}
                                        className={`flex items-center gap-3 p-2.5 rounded-lg transition-colors ${
                                            entry.status === "success"
                                                ? "hover:bg-emerald-50 cursor-pointer"
                                                : "hover:bg-slate-50"
                                        } ${selectedFileIndex === idx ? "ring-2 ring-blue-400 bg-blue-50" : ""}`}
                                        onClick={() => entry.status === "success" && handleSelectFile(idx)}
                                    >
                                        <div
                                            className={`w-2.5 h-2.5 rounded-full shrink-0 ${statusColor[entry.status]}`}/>
                                        <FileText className={`w-5 h-5 shrink-0 ${
                                            entry.status === "success" ? "text-emerald-500" :
                                                entry.status === "error" ? "text-red-400" :
                                                    entry.status === "processing" ? "text-blue-500" : "text-slate-400"
                                        }`}/>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-slate-800 truncate">{entry.file.name}</p>
                                            <p className="text-xs text-slate-400">
                                                {(entry.file.size / 1024).toFixed(1)} KB
                                                {entry.result && (
                                                    <span className="ml-2 text-emerald-600">
                                                        {DOC_TYPE_KEYS[entry.result.doc_type] ? t(DOC_TYPE_KEYS[entry.result.doc_type]) : entry.result.doc_type}
                                                    </span>
                                                )}
                                            </p>
                                        </div>
                                        <span className={`text-xs font-medium whitespace-nowrap ${
                                            entry.status === "success" ? "text-emerald-600" :
                                                entry.status === "error" ? "text-red-600" :
                                                    entry.status === "processing" ? "text-blue-600" : "text-slate-400"
                                        }`}>
                                            {entry.status === "error" && entry.error
                                                ? entry.error.slice(0, 30)
                                                : statusLabel[entry.status]
                                            }
                                        </span>
                                        {entry.status === "waiting" && !isProcessing && (
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    removeFile(idx);
                                                }}
                                                className="text-slate-400 hover:text-red-500 transition-colors text-lg leading-none px-1"
                                            >&times;</button>
                                        )}
                                    </div>
                                ))}
                            </div>
                            {/* 图片预览 */}
                            {preview && (
                                <div className="mt-2 border border-slate-200 rounded-xl overflow-hidden">
                                    <img src={preview} alt="预览" className="max-h-64 mx-auto object-contain"/>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* ===== 填充中 ===== */}
            {view === "filling" && (
                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-16 text-center">
                    <Loader2 className="w-12 h-12 text-blue-500 mx-auto mb-4 animate-spin"/>
                    <p className="text-lg text-slate-700 font-medium">{t("processing.filling")}</p>
                    <p className="text-sm text-slate-400 mt-2">{t("processing.hint")}</p>
                </div>
            )}

            {/* ===== 复核视图 ===== */}
            {view === "review" && selectedResult && (
                <div className="space-y-6">
                    {/* 返回主页按钮 */}
                    <button
                        onClick={handleGoHome}
                        className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1 transition-colors"
                    >
                        <Home className="w-4 h-4"/>
                        {t("step.upload")}
                    </button>

                    {/* 文件切换器（多文件时） */}
                    {files.filter(f => f.status === "success").length > 1 && (
                        <div className="flex gap-2 flex-wrap">
                            {files.map((entry, idx) => entry.status === "success" && (
                                <button
                                    key={idx}
                                    onClick={() => handleSelectFile(idx)}
                                    className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                                        selectedFileIndex === idx
                                            ? "bg-blue-600 text-white"
                                            : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                                    }`}
                                >
                                    {entry.file.name}
                                </button>
                            ))}
                        </div>
                    )}

                    {/* 自动分类结果 */}
                    {selectedFile?.classifyInfo && (
                        <div className="bg-blue-50 border border-blue-200 rounded-2xl p-4 flex items-center gap-3">
                            {DOC_ICONS[selectedFile.classifyInfo.doc_type] || <FileText className="w-5 h-5"/>}
                            <div className="text-left">
                                <p className="text-sm font-medium text-blue-800">
                                    {t("review.classify")}: {DOC_TYPE_KEYS[selectedFile.classifyInfo.doc_type] ? t(DOC_TYPE_KEYS[selectedFile.classifyInfo.doc_type]) : selectedFile.classifyInfo.doc_type}
                                    <span
                                        className="ml-2 text-xs text-blue-500">({selectedFile.classifyInfo.confidence})</span>
                                </p>
                                <p className="text-xs text-blue-600">{selectedFile.classifyInfo.description}</p>
                            </div>
                        </div>
                    )}

                    {/* 识别概览 */}
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-base font-semibold text-slate-700">{t("review.title")}</h2>
                            <span
                                className="px-3 py-1 bg-emerald-100 text-emerald-700 rounded-full text-sm font-medium flex items-center gap-1">
                                {DOC_ICONS[selectedResult.doc_type]}
                                {DOC_TYPE_KEYS[selectedResult.doc_type] ? t(DOC_TYPE_KEYS[selectedResult.doc_type]) : selectedResult.doc_type}
                            </span>
                        </div>
                        <div className="grid grid-cols-3 gap-4 text-center">
                            <div className="bg-slate-50 rounded-xl p-4">
                                <p className="text-2xl font-bold text-slate-800">{selectedResult.pages}</p>
                                <p className="text-sm text-slate-500">{t("review.pages")}</p>
                            </div>
                            <div className="bg-slate-50 rounded-xl p-4">
                                <p className="text-2xl font-bold text-slate-800">{selectedResult.results.length}</p>
                                <p className="text-sm text-slate-500">{t("review.records")}</p>
                            </div>
                            <div className="bg-slate-50 rounded-xl p-4">
                                <p className="text-2xl font-bold text-slate-800">{selectedResult.warnings.length}</p>
                                <p className="text-sm text-slate-500">{t("review.warnings")}</p>
                            </div>
                        </div>
                    </div>

                    {/* 警告列表 */}
                    {selectedResult.warnings.length > 0 && (
                        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
                            <h3 className="font-medium text-amber-800 mb-2 flex items-center gap-2">
                                <AlertCircle className="w-4 h-4"/>
                                {t("review.warnings")}
                            </h3>
                            <ul className="space-y-1">
                                {selectedResult.warnings.map((w, i) => (
                                    <li key={i} className="text-sm text-amber-700">• {w}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {/* 数据预览 */}
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                        <h3 className="font-medium text-slate-700 mb-3">{t("review.data_preview")}</h3>
                        <div className="max-h-[48rem] overflow-auto">
                            {selectedResult.results.map((rec, ri) => {
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
                                                <div
                                                    className="mt-2 mb-2 border border-slate-200 rounded-lg overflow-hidden max-h-64">
                                                    <img src={cropUrl} alt={`${t("review.record")} ${ri + 1}`}
                                                         className="w-full object-contain max-h-64"/>
                                                </div>
                                            )}
                                            <pre
                                                className="text-xs bg-slate-50 rounded-lg p-3 mt-1 whitespace-pre-wrap">
                                                {JSON.stringify(rec, null, 2).slice(0, 2000)}
                                            </pre>
                                        </details>
                                    );
                                }
                                const cols = Object.keys(entries[0]).filter(
                                    (k) => k !== "needs_review" && k !== "review_reason"
                                );
                                return (
                                    <details key={ri} open={selectedResult.results.length === 1} className="mb-3">
                                        <summary className="text-sm font-medium text-slate-600 cursor-pointer">
                                            {t("review.record")} {ri + 1} — {entries.length} {t("review.rows")}
                                        </summary>
                                        {cropUrl && (
                                            <div
                                                className="mt-2 mb-3 border border-slate-200 rounded-lg overflow-hidden">
                                                <p className="text-xs text-slate-500 bg-slate-50 px-3 py-1 border-b border-slate-200">
                                                    {t("review.crop_hint")}
                                                </p>
                                                <a href={cropUrl} target="_blank" rel="noopener noreferrer">
                                                    <img src={cropUrl} alt={`${t("review.record")} ${ri + 1}`}
                                                         className="w-full object-contain max-h-72 cursor-zoom-in"/>
                                                </a>
                                            </div>
                                        )}
                                        <div className="overflow-x-auto mt-2">
                                            <table className="min-w-full text-xs border-collapse">
                                                <thead>
                                                <tr className="bg-slate-100">
                                                    {cols.map((c) => (
                                                        <th key={c}
                                                            className="px-2 py-1 border border-slate-200 text-left font-medium text-slate-600 whitespace-nowrap">{c}</th>
                                                    ))}
                                                </tr>
                                                </thead>
                                                <tbody>
                                                {entries.slice(0, 50).map((row, rIdx) => (
                                                    <tr key={rIdx}
                                                        className={rIdx % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                                                        {cols.map((c) => (
                                                            <td key={c}
                                                                className="px-2 py-1 border border-slate-200 text-slate-700 whitespace-nowrap">{String(row[c] ?? "")}</td>
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
                            onClick={handleGoHome}
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

            {/* ===== 完成视图 ===== */}
            {view === "done" && fillResult && (
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
                            onClick={handleGoHome}
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
