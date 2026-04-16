import React, {useCallback, useEffect, useRef, useState} from "react";
import {Link, Route, Routes, useLocation, useNavigate} from "react-router-dom";
import {
    AlertCircle,
    BarChart3,
    CheckCircle,
    Circle,
    ClipboardList,
    Clock,
    Download,
    FileText,
    Home,
    Loader2,
    Package,
    Pause,
    Play,
    ScanLine,
    Scissors,
    Settings,
    TreePine,
    Truck,
    Upload,
    X,
} from "lucide-react";
import {useT, setLocale, type Locale} from "./i18n";
import SettingsPanel from "./SettingsPanel";
import HistoryPanel from "./HistoryPanel";
import DashboardPanel from "./DashboardPanel";
import {
    type BatchErrorEvent,
    type BatchProgressEvent,
    type BatchResultEvent,
    type ClassifyResult,
    DOC_TYPE_KEYS,
    extractErrorMessage,
    fillExcel,
    type FillResult,
    getPlatform,
    getScanDevices,
    getSettings,
    getUpdateStatus,
    healthCheck,
    processBatch,
    type ProcessResult,
    scanAcquire,
    type ScannerDevice,
    type UpdateStatus,
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
type FileStatus = "waiting" | "processing" | "paused" | "success" | "error";

interface FileEntry {
    file: File;
    status: FileStatus;
    progress: number;
    progressStage: string;
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

    /* 更新通知 toast */
    const [updateToast, setUpdateToast] = useState<UpdateStatus | null>(null);

    /* 扫描仪状态 */
    const [scanAvailable, setScanAvailable] = useState(false);
    const [scanDevices, setScanDevices] = useState<ScannerDevice[]>([]);
    const [scanSelectedDevice, setScanSelectedDevice] = useState("");
    const [scanning, setScanning] = useState(false);
    const [scanMsg, setScanMsg] = useState("");

    /* 派生状态 */
    const isProcessing = files.some(f => f.status === "processing");
    const selectedFile = selectedFileIndex >= 0 ? files[selectedFileIndex] : null;
    const selectedResult = selectedFile?.result ?? null;

    useEffect(() => {
        healthCheck()
            .then(() => {
                setBackendOk(true);
                return getSettings();
            })
            .then((res) => {
                if (res.settings.language) {
                    setLocale(res.settings.language as Locale);
                }
                if (!res.settings.openai_api_key_set) {
                    setNeedsSetup(true);
                    navigate("/settings");
                }
            })
            .catch(() => setBackendOk(false));
        // 桌面端：轮询更新状态
        getPlatform()
            .then((p) => {
                if (!p.desktop) return;
                const poll = setInterval(() => {
                    getUpdateStatus()
                        .then((s) => {
                            if (s.status === "ready" || s.status === "downloading") {
                                setUpdateToast(s);
                            }
                            if (s.status === "ready" || s.status === "error" || s.status === "idle") {
                                clearInterval(poll);
                            }
                        })
                        .catch(() => clearInterval(poll));
                }, 5000);
                // 60秒后停止轮询
                setTimeout(() => clearInterval(poll), 60000);
            })
            .catch(() => {});
        // 检测扫描仪可用性
        getScanDevices()
            .then((res) => {
                setScanAvailable(res.available);
                setScanDevices(res.devices);
                if (res.devices.length > 0) setScanSelectedDevice(res.devices[0].device_id);
            })
            .catch(() => setScanAvailable(false));
    }, []);

    const addFiles = useCallback((newFiles: FileList | File[]) => {
        const arr = Array.from(newFiles);
        setFiles(prev => [
            ...prev,
            ...arr.map(f => ({file: f, status: "waiting" as FileStatus, progress: 0, progressStage: ""})),
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

    const handleScan = useCallback(async () => {
        setScanning(true);
        setScanMsg("");
        try {
            const res = await scanAcquire(scanSelectedDevice || undefined);
            // 将扫描得到的文件加入列表（从后端下载）
            const resp = await fetch(`/api/scan/file/${res.filename}`);
            const blob = await resp.blob();
            const file = new File([blob], res.filename, {type: blob.type || "image/png"});
            addFiles([file]);
            setScanMsg(t("upload.scan_success"));
        } catch (err) {
            setScanMsg(t("upload.scan_error") + ": " + extractErrorMessage(err));
        } finally {
            setScanning(false);
            setTimeout(() => setScanMsg(""), 5000);
        }
    }, [scanSelectedDevice, addFiles, t]);

    /* 开始处理：只处理 waiting 状态的文件，不影响已完成的 */
    const handleProcess = useCallback(() => {
        const pendingIndices = files
            .map((f, i) => (f.status === "waiting" || f.status === "paused") ? i : -1)
            .filter(i => i >= 0);
        if (pendingIndices.length === 0) return;

        setError(null);

        // 标记为 processing（paused 文件保留已有进度，waiting 从零开始）
        setFiles(prev => prev.map((f, i) =>
            pendingIndices.includes(i)
                ? {
                    ...f,
                    status: "processing" as FileStatus,
                    progress: f.status === "paused" ? f.progress : 0,
                    progressStage: f.status === "paused" ? f.progressStage : "",
                    error: undefined,
                    result: undefined,
                    classifyInfo: undefined,
                }
                : f
        ));

        const rawFiles = pendingIndices.map(i => files[i].file);

        // 统一走 SSE 批量处理
        batchAbortRef.current = processBatch(rawFiles, docType, {
            onProgress: (e: BatchProgressEvent) => {
                const fileIdx = pendingIndices[e.index];
                setFiles(prev => prev.map((f, i) => i === fileIdx ? {
                    ...f,
                    status: "processing",
                    progress: e.percent,
                    progressStage: e.stage,
                } : f));
            },
            onResult: (e: BatchResultEvent) => {
                const fileIdx = pendingIndices[e.index];
                setFiles(prev => prev.map((f, i) => i === fileIdx ? {
                    ...f,
                    status: "success",
                    progress: 100,
                    progressStage: "",
                    result: e.data,
                } : f));
            },
            onError: (e: BatchErrorEvent) => {
                const fileIdx = pendingIndices[e.index];
                setFiles(prev => prev.map((f, i) => i === fileIdx ? {
                    ...f,
                    status: "error",
                    error: e.error,
                } : f));
            },
            onDone: () => {
                batchAbortRef.current = null;
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

    /* 中断全部处理 */
    const handleAbortAll = useCallback(() => {
        if (batchAbortRef.current) {
            batchAbortRef.current.abort();
            batchAbortRef.current = null;
        }
        setFiles(prev => prev.map(f =>
            f.status === "processing" ? {...f, status: "paused" as FileStatus, progressStage: "upload.file_paused"} : f
        ));
    }, []);

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

    const handleDownload = useCallback(async () => {
        if (!fillResult) return;
        try {
            const resp = await fetch(fillResult.download_url);
            if (!resp.ok) { setError(`下载失败: HTTP ${resp.status}`); return; }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = fillResult.filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (err) {
            setError(extractErrorMessage(err));
        }
    }, [fillResult]);

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
            progress: 100,
            progressStage: "",
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
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-primary-50">
            {/* 顶栏 */}
            <header className="bg-white/80 backdrop-blur border-b border-slate-200 sticky top-0 z-10">
                <div className="max-w-5xl mx-auto px-6 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <button onClick={() => {
                            handleGoHome();
                            navigate("/");
                        }} className="flex items-center gap-3 hover:opacity-80 transition-opacity">
                            <ScanLine className="w-7 h-7 text-emerald-600"/>
                            <h1 className="text-lg font-semibold text-slate-800">
                                {t("app.title")}
                            </h1>
                        </button>
                        <p className="text-sm text-slate-500 hidden sm:block">
                            {t("app.subtitle")}
                        </p>
                        {backendOk !== null && (
                            <span
                                className={`w-2 h-2 rounded-full ${
                                    backendOk ? "bg-emerald-500" : "bg-red-400"
                                }`}
                                title={backendOk ? t("error.backend_online") : t("error.backend_offline")}
                            />
                        )}
                    </div>
                    <div className="flex items-center gap-1">
                        {navItems.map((item) => (
                            <Link
                                key={item.to}
                                to={item.to}
                                className={`p-2 rounded-lg transition-colors flex items-center gap-1.5 text-sm ${
                                    location.pathname === item.to
                                        ? "bg-primary-50 text-primary-600"
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
                            handleAbortAll={handleAbortAll}
                            handleFill={handleFill}
                            handleDownload={handleDownload}
                            handleReset={handleReset}
                            handleGoHome={handleGoHome}
                            scanAvailable={scanAvailable}
                            scanDevices={scanDevices}
                            scanSelectedDevice={scanSelectedDevice}
                            setScanSelectedDevice={setScanSelectedDevice}
                            scanning={scanning}
                            scanMsg={scanMsg}
                            handleScan={handleScan}
                        />
                    }/>
                </Routes>
            </main>

            {/* ===== 更新通知 toast（右下角） ===== */}
            {updateToast && (updateToast.status === "ready" || updateToast.status === "downloading") && (
                <div className="fixed bottom-6 right-6 z-50 max-w-sm bg-white border border-slate-200 rounded-xl shadow-lg p-4 flex items-start gap-3">
                    {updateToast.status === "downloading" ? (
                        <Loader2 className="w-5 h-5 text-primary-500 animate-spin shrink-0 mt-0.5"/>
                    ) : (
                        <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5"/>
                    )}
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-800">
                            {updateToast.status === "downloading"
                                ? `${t("settings.update_checking")} ${updateToast.progress}%`
                                : updateToast.message}
                        </p>
                        {updateToast.status === "downloading" && (
                            <div className="w-full h-1.5 bg-slate-100 rounded-full mt-2 overflow-hidden">
                                <div
                                    className="h-full bg-primary-500 rounded-full transition-all"
                                    style={{width: `${updateToast.progress}%`}}
                                />
                            </div>
                        )}
                    </div>
                    <button onClick={() => setUpdateToast(null)} className="text-slate-400 hover:text-slate-600">
                        <X className="w-4 h-4"/>
                    </button>
                </div>
            )}
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
                            handleProcess, handleAbortAll, handleFill, handleDownload, handleReset, handleGoHome,
                            scanAvailable, scanDevices, scanSelectedDevice, setScanSelectedDevice,
                            scanning, scanMsg, handleScan,
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
    handleAbortAll: () => void;
    handleFill: () => void;
    handleDownload: () => void;
    handleReset: () => void;
    handleGoHome: () => void;
    scanAvailable: boolean;
    scanDevices: ScannerDevice[];
    scanSelectedDevice: string;
    setScanSelectedDevice: (id: string) => void;
    scanning: boolean;
    scanMsg: string;
    handleScan: () => void;
}) {
    const statusLabel: Record<FileStatus, string> = {
        waiting: t("upload.file_waiting"),
        processing: t("upload.file_processing"),
        paused: t("upload.file_paused"),
        success: t("upload.file_success"),
        error: t("upload.file_error"),
    };

    /** 解析后端发送的结构化 stage key 并翻译 */
    const translateStage = (stage: string): string => {
        if (!stage) return "";
        // 格式: "progress.extracting:doc_type:current:total"
        if (stage.startsWith("progress.extracting:")) {
            const parts = stage.split(":");
            const docType = parts[1] || "";
            const current = parts[2] || "";
            const total = parts[3] || "";
            const typeName = DOC_TYPE_KEYS[docType] ? t(DOC_TYPE_KEYS[docType]) : docType;
            return t("progress.extracting")
                .replace("{type}", typeName)
                .replace("{current}", current)
                .replace("{total}", total);
        }
        // 其他 key 直接翻译
        const translated = t(stage);
        return translated !== stage ? translated : stage;
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
    const hasWaiting = files.some(f => f.status === "waiting" || f.status === "paused");

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
                                    active ? "bg-primary-600 text-white"
                                        : completed ? "bg-emerald-500 text-white"
                                            : "bg-slate-200 text-slate-500"
                                }`}>
                                {completed ? <CheckCircle className="w-4 h-4"/> : i + 1}
                            </div>
                            <span className={`text-sm ${active ? "text-primary-700 font-medium" : "text-slate-500"}`}>
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
                                            ? "border-primary-500 bg-primary-50 text-primary-700 shadow-sm"
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

                    {/* 文件上传区 + 扫描仪面板 */}
                    <div className={`grid gap-4 ${scanAvailable ? "grid-cols-3" : "grid-cols-1"}`}>
                        {/* 拖放上传区 */}
                        <div
                            className={`${scanAvailable ? "col-span-2" : ""} bg-white rounded-2xl shadow-sm border-2 border-dashed transition-colors p-12 text-center cursor-pointer ${
                                dragging ? "border-primary-500 bg-primary-50" : "border-slate-300 hover:border-primary-400"
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
                            <Upload className={`w-12 h-12 mx-auto mb-4 ${dragging ? "text-primary-500" : "text-slate-400"}`}/>
                            <p className="text-slate-600 font-medium">{t("upload.hint")}</p>
                            <p className="text-sm text-slate-400 mt-2">{t("upload.supported")}</p>
                        </div>

                        {/* 扫描仪面板（仅在检测到可用时显示） */}
                        {scanAvailable && (
                        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 flex flex-col items-center justify-center text-center space-y-4">
                            <ScanLine className="w-10 h-10 text-violet-500"/>
                            <p className="text-sm font-medium text-slate-700">{t("upload.scan")}</p>
                            {scanDevices.length > 1 && (
                                <select
                                    value={scanSelectedDevice}
                                    onChange={(e) => setScanSelectedDevice(e.target.value)}
                                    className="w-full text-xs border border-slate-200 rounded-lg px-2 py-1.5 focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                                >
                                    {scanDevices.map((d) => (
                                        <option key={d.device_id} value={d.device_id}>{d.name}</option>
                                    ))}
                                </select>
                            )}
                            {scanDevices.length === 1 && (
                                <p className="text-xs text-slate-400 truncate w-full">{scanDevices[0].name}</p>
                            )}
                            {scanDevices.length === 0 && (
                                <p className="text-xs text-amber-500">{t("upload.scan_no_device")}</p>
                            )}
                            <button
                                onClick={handleScan}
                                disabled={scanning || scanDevices.length === 0}
                                className="w-full px-4 py-2.5 bg-violet-600 text-white rounded-xl hover:bg-violet-700 transition-colors text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50"
                            >
                                {scanning ? (
                                    <><Loader2 className="w-4 h-4 animate-spin"/>{t("upload.scan_scanning")}</>
                                ) : (
                                    <><ScanLine className="w-4 h-4"/>{t("upload.scan")}</>
                                )}
                            </button>
                            {scanMsg && (
                                <p className={`text-xs ${scanMsg.includes(t("upload.scan_error")) ? "text-red-500" : "text-emerald-600"}`}>
                                    {scanMsg}
                                </p>
                            )}
                        </div>
                        )}
                    </div>

                    {/* 文件列表 */}
                    {files.length > 0 && (
                        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-3">
                            <div className="flex items-center justify-between mb-2">
                                <p className="text-sm font-medium text-slate-600">
                                    {t("upload.files_selected").replace("{n}", String(files.length))}
                                    {isProcessing && (
                                        <span className="ml-2 inline-flex items-center gap-1 text-primary-600">
                                            <Loader2 className="w-3.5 h-3.5 animate-spin"/>
                                            {t("upload.file_processing")}
                                        </span>
                                    )}
                                </p>
                                <div className="flex gap-2">
                                    {hasWaiting && !isProcessing && (
                                        <button
                                            onClick={handleProcess}
                                            className="px-5 py-2 bg-primary-600 text-white rounded-xl hover:bg-primary-700 transition-colors font-medium flex items-center gap-2 text-sm"
                                        >
                                            <Play className="w-4 h-4"/>
                                            {t("upload.start")}
                                        </button>
                                    )}
                                    {isProcessing && (
                                        <button
                                            onClick={handleAbortAll}
                                            className="px-5 py-2 bg-amber-500 text-white rounded-xl hover:bg-amber-600 transition-colors font-medium flex items-center gap-2 text-sm"
                                        >
                                            <Pause className="w-4 h-4"/>
                                            {t("upload.pause")}
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
                            <div className="divide-y divide-slate-100 max-h-96 overflow-auto">
                                {files.map((entry, idx) => (
                                    <div key={idx}
                                         className={`transition-colors ${
                                             entry.status === "success"
                                                 ? "hover:bg-emerald-50 cursor-pointer"
                                                 : "hover:bg-slate-50"
                                         } ${selectedFileIndex === idx ? "ring-2 ring-primary-400 bg-primary-50" : ""}`}
                                         onClick={() => entry.status === "success" && handleSelectFile(idx)}
                                    >
                                        <div className="flex items-center gap-3 px-3 py-2.5">
                                            {/* 状态图标 */}
                                            {entry.status === "processing" ? (
                                                <Loader2 className="w-4 h-4 shrink-0 text-primary-500 animate-spin"/>
                                            ) : entry.status === "success" ? (
                                                <CheckCircle className="w-4 h-4 shrink-0 text-emerald-500"/>
                                            ) : entry.status === "error" ? (
                                                <AlertCircle className="w-4 h-4 shrink-0 text-red-400"/>
                                            ) : entry.status === "paused" ? (
                                                <Pause className="w-4 h-4 shrink-0 text-amber-500"/>
                                            ) : (
                                                <Circle className="w-4 h-4 shrink-0 text-slate-300"/>
                                            )}
                                            {/* 文件信息 */}
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm font-medium text-slate-800 truncate">{entry.file.name}</p>
                                                <p className="text-xs text-slate-400">
                                                    {(entry.file.size / 1024).toFixed(1)} KB
                                                    {entry.progressStage && (
                                                        <span
                                                            className="ml-2 text-primary-500">{translateStage(entry.progressStage)}</span>
                                                    )}
                                                    {entry.result && (
                                                        <span className="ml-2 text-emerald-600">
                                                            {DOC_TYPE_KEYS[entry.result.doc_type] ? t(DOC_TYPE_KEYS[entry.result.doc_type]) : entry.result.doc_type}
                                                        </span>
                                                    )}
                                                </p>
                                            </div>
                                            {/* 百分比 */}
                                            {(entry.status === "processing" || entry.status === "paused") && (
                                                <span
                                                    className="text-xs font-mono text-primary-600 w-10 text-right shrink-0">
                                                    {entry.progress}%
                                                </span>
                                            )}
                                            {/* 状态标签 */}
                                            {(entry.status === "success" || entry.status === "error") && (
                                                <span className={`text-xs font-medium whitespace-nowrap ${
                                                    entry.status === "success" ? "text-emerald-600" : "text-red-600"
                                                }`}>
                                                    {entry.status === "error" && entry.error
                                                        ? entry.error.slice(0, 30)
                                                        : statusLabel[entry.status]
                                                    }
                                                </span>
                                            )}
                                            {/* 操作按钮 */}
                                            <div className="flex items-center gap-1 shrink-0">
                                                {entry.status === "processing" && (
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleAbortAll();
                                                        }}
                                                        className="p-1 text-slate-400 hover:text-amber-500 transition-colors"
                                                        title={t("upload.pause")}
                                                    >
                                                        <Pause className="w-3.5 h-3.5"/>
                                                    </button>
                                                )}
                                                {entry.status === "paused" && (
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleProcess();
                                                        }}
                                                        className="p-1 text-slate-400 hover:text-emerald-500 transition-colors"
                                                        title={t("upload.resume")}
                                                    >
                                                        <Play className="w-3.5 h-3.5"/>
                                                    </button>
                                                )}
                                                {(entry.status === "waiting" || entry.status === "paused" || entry.status === "error") && (
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            removeFile(idx);
                                                        }}
                                                        className="p-1 text-slate-400 hover:text-red-500 transition-colors"
                                                        title={t("upload.remove")}
                                                    >
                                                        <X className="w-3.5 h-3.5"/>
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                        {/* 真实进度条 */}
                                        {(entry.status === "processing" || entry.status === "paused") && (
                                            <div className="h-1 bg-slate-100">
                                                <div
                                                    className={`h-full transition-all duration-500 ${
                                                        entry.status === "paused" ? "bg-amber-400" : "bg-primary-500"
                                                    }`}
                                                    style={{width: `${entry.progress}%`}}
                                                />
                                            </div>
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
                    <Loader2 className="w-12 h-12 text-primary-500 mx-auto mb-4 animate-spin"/>
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
                        className="text-sm text-primary-600 hover:text-primary-800 flex items-center gap-1 transition-colors"
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
                                            ? "bg-primary-600 text-white"
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
                        <div className="bg-primary-50 border border-primary-200 rounded-2xl p-4 flex items-center gap-3">
                            {DOC_ICONS[selectedFile.classifyInfo.doc_type] || <FileText className="w-5 h-5"/>}
                            <div className="text-left">
                                <p className="text-sm font-medium text-primary-800">
                                    {t("review.classify")}: {DOC_TYPE_KEYS[selectedFile.classifyInfo.doc_type] ? t(DOC_TYPE_KEYS[selectedFile.classifyInfo.doc_type]) : selectedFile.classifyInfo.doc_type}
                                    <span
                                        className="ml-2 text-xs text-primary-500">({selectedFile.classifyInfo.confidence})</span>
                                </p>
                                <p className="text-xs text-primary-600">{selectedFile.classifyInfo.description}</p>
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
                                /* 字段列表格式：[{field_name, value, ...}] → 双列表格 */
                                const isFieldList = entries.length > 0 && "field_name" in entries[0] && "value" in entries[0];

                                if (isFieldList) {
                                    return (
                                        <details key={ri} open={selectedResult.results.length === 1} className="mb-3">
                                            <summary className="text-sm font-medium text-slate-600 cursor-pointer">
                                                {t("review.record")} {ri + 1}
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
                                            <div className="overflow-x-auto mt-2 border border-slate-200 rounded-lg">
                                                <table className="min-w-full text-sm">
                                                    <thead>
                                                    <tr className="bg-slate-100">
                                                        <th className="px-3 py-2 text-left font-medium text-slate-600 border-b border-slate-200 w-1/3">{t("history.field_name")}</th>
                                                        <th className="px-3 py-2 text-left font-medium text-slate-600 border-b border-slate-200">{t("history.field_value")}</th>
                                                    </tr>
                                                    </thead>
                                                    <tbody>
                                                    {entries.map((f, fi) => (
                                                        <tr key={fi}
                                                            className={fi % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                                                            <td className="px-3 py-1.5 border-b border-slate-100 text-slate-500 text-xs">
                                                                {t(`field.${f.field_name}`) !== `field.${f.field_name}` ? `${t(`field.${f.field_name}`)} (${f.field_name})` : String(f.field_name ?? "")}
                                                            </td>
                                                            <td className="px-3 py-1.5 border-b border-slate-100 text-slate-900">{String(f.value ?? "—")}</td>
                                                        </tr>
                                                    ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </details>
                                    );
                                }

                                /* 表格行格式：[{col1, col2, ...}] → 多列表格 */
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
                                                            className="px-2 py-1 border border-slate-200 text-left font-medium text-slate-600 whitespace-nowrap">{t(`field.${c}`) !== `field.${c}` ? `${t(`field.${c}`)} (${c})` : c}</th>
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
                        <button
                            onClick={handleDownload}
                            className="px-6 py-2.5 bg-primary-600 text-white rounded-xl hover:bg-primary-700 transition-colors font-medium inline-flex items-center gap-2"
                        >
                            <Download className="w-4 h-4"/>
                            {t("done.download")}
                        </button>
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
