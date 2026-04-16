import {useState, useEffect, useCallback, useRef} from "react";
import {
    Settings as SettingsIcon,
    Eye,
    EyeOff,
    Download,
    ExternalLink,
    Loader2,
    CheckCircle,
    AlertCircle,
    RefreshCw,
    Power,
    Info,
    Minimize2,
    LogOut,
    RotateCcw,
} from "lucide-react";
import {
    getSettings,
    updateSettings,
    getPlatform,
    getAutostart,
    setAutostart as apiSetAutostart,
    getCloseBehavior,
    setCloseBehavior as apiSetCloseBehavior,
    resetWindow as apiResetWindow,
    checkUpdate,
    getAutoUpdate,
    setAutoUpdate as apiSetAutoUpdate,
    getUpdateStatus,
    triggerUpdateDownload,
    extractErrorMessage,
    type UserSettings,
    type ModelInfo,
    type VersionInfo,
    type CloseBehavior,
    type UpdateStatus,
} from "./api";
import {getCurrentLocale, setLocale, LOCALE_OPTIONS, useT, type Locale} from "./i18n";

interface Props {
    onSettingsChange?: () => void;
}

export default function SettingsPanel({onSettingsChange}: Props) {
    const t = useT();
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [currentSettings, setCurrentSettings] = useState<UserSettings | null>(null);
    const [models, setModels] = useState<ModelInfo[]>([]);

    // 表单状态
    const [apiKey, setApiKey] = useState("");
    const [showKey, setShowKey] = useState(false);
    const [selectedModel, setSelectedModel] = useState("");
    const [baseUrl, setBaseUrl] = useState("");
    const [language, setLanguage] = useState<Locale>(getCurrentLocale());

    // 开机自启状态
    const [autostart, setAutostartState] = useState(false);
    const [autostartLoading, setAutostartLoading] = useState(false);

    // 关闭行为
    const [closeBehavior, setCloseBehaviorState] = useState<CloseBehavior>("minimize_to_tray");

    // 重置窗口
    const [resetMsg, setResetMsg] = useState<string | null>(null);

    // 平台检测
    const [isDesktop, setIsDesktop] = useState(false);
    const [appVersion, setAppVersion] = useState("");

    // 版本与更新（桌面专属）
    const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
    const [updateLoading, setUpdateLoading] = useState(false);
    const [updateError, setUpdateError] = useState<string | null>(null);

    // 自动更新
    const [autoUpdate, setAutoUpdateState] = useState(false);
    const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);

    // 加载设置
    useEffect(() => {
        setLoading(true);
        setError(null);
        setSaved(false);
        Promise.all([
            getSettings(),
            getPlatform().catch(() => ({desktop: false, version: ""})),
            getAutostart().catch(() => ({enabled: false})),
            getCloseBehavior().catch(() => ({behavior: "minimize_to_tray" as CloseBehavior})),
            getAutoUpdate().catch(() => ({enabled: false})),
            getUpdateStatus().catch(() => null),
        ])
            .then(([res, platformRes, autostartRes, closeBehaviorRes, autoUpdateRes, updateStatusRes]) => {
                setCurrentSettings(res.settings);
                setModels(res.available_models);
                setSelectedModel(res.settings.openai_model);
                setBaseUrl(res.settings.openai_base_url);
                setApiKey("");
                setIsDesktop(platformRes.desktop);
                setAppVersion(platformRes.version);
                setAutostartState(autostartRes.enabled);
                setCloseBehaviorState(closeBehaviorRes.behavior);
                setAutoUpdateState(autoUpdateRes.enabled);
                if (updateStatusRes) setUpdateStatus(updateStatusRes);
            })
            .catch((err) => setError(extractErrorMessage(err)))
            .finally(() => {
                setLoading(false);
                requestAnimationFrame(() => { initialized.current = true; });
            });
    }, []);

    /** 是否已完成初始化（避免加载时触发自动保存） */
    const initialized = useRef(false);

    const doSave = useCallback(async (overrides: Record<string, string> = {}) => {
        if (!initialized.current) return;
        setSaving(true);
        setError(null);
        setSaved(false);
        try {
            const body: Record<string, string> = {
                openai_model: selectedModel,
                openai_base_url: baseUrl,
                language: language,
                ...overrides,
            };
            const res = await updateSettings(body);
            setCurrentSettings(res.settings);
            setLocale(language);
            setSaved(true);
            onSettingsChange?.();
            setTimeout(() => setSaved(false), 3000);
        } catch (err) {
            setError(extractErrorMessage(err));
        } finally {
            setSaving(false);
        }
    }, [selectedModel, baseUrl, language]);

    /** model / language 变化时立即保存 */
    useEffect(() => {
        if (!initialized.current) return;
        doSave();
    }, [selectedModel, language]);

    /** API Key / Base URL 失焦时保存 */
    const handleBlurSave = useCallback(() => {
        const overrides: Record<string, string> = {};
        if (apiKey.trim()) {
            overrides.openai_api_key = apiKey.trim();
        }
        doSave(overrides).then(() => {
            if (apiKey.trim()) setApiKey("");
        });
    }, [apiKey, doSave]);

    return (
        <div className="max-w-xl space-y-6">
            <div className="flex items-center gap-2 mb-2">
                <SettingsIcon className="w-6 h-6 text-slate-600"/>
                <h2 className="text-xl font-semibold text-slate-800">{t("settings.title")}</h2>
            </div>

            {loading ? (
                <div className="p-12 text-center">
                    <Loader2 className="w-8 h-8 text-primary-500 mx-auto animate-spin"/>
                    <p className="text-sm text-slate-500 mt-2">{t("settings.loading")}</p>
                </div>
            ) : (
                <div className="space-y-6">
                        {/* API Key */}
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-1">
                                {t("settings.api_key")}
                            </label>
                            {currentSettings?.openai_api_key_set && (
                                <p className="text-xs text-slate-400 mb-2">
                                    {t("settings.api_key_current").replace("{masked}", currentSettings.openai_api_key_masked)}
                                </p>
                            )}
                            <div className="relative">
                                <input
                                    type={showKey ? "text" : "password"}
                                    value={apiKey}
                                    onChange={(e) => setApiKey(e.target.value)}
                                    onBlur={handleBlurSave}
                                    placeholder={
                                        currentSettings?.openai_api_key_set
                                            ? t("settings.api_key_placeholder")
                                            : "sk-..."
                                    }
                                    className="w-full px-4 py-2.5 pr-10 border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowKey(!showKey)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                                >
                                    {showKey ? (
                                        <EyeOff className="w-4 h-4"/>
                                    ) : (
                                        <Eye className="w-4 h-4"/>
                                    )}
                                </button>
                            </div>
                            {!currentSettings?.openai_api_key_set && (
                                <p className="text-xs text-amber-600 mt-1 flex items-center gap-1">
                                    <AlertCircle className="w-3 h-3"/>
                                    {t("settings.api_key_missing")}
                                </p>
                            )}
                        </div>

                        {/* 模型选择 */}
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-2">
                                {t("settings.model")}
                            </label>
                            <div className="space-y-2">
                                {models.map((m) => (
                                    <label
                                        key={m.id}
                                        className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                                            selectedModel === m.id
                                                ? "border-primary-500 bg-primary-50"
                                                : "border-slate-200 hover:border-slate-300"
                                        }`}
                                    >
                                        <input
                                            type="radio"
                                            name="model"
                                            value={m.id}
                                            checked={selectedModel === m.id}
                                            onChange={() => setSelectedModel(m.id)}
                                            className="mt-1"
                                        />
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                        <span className="font-medium text-sm text-slate-800">
                          {m.name}
                        </span>
                                                <span
                                                    className="text-xs bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
                          {m.provider}
                        </span>
                                            </div>
                                            <p className="text-xs text-slate-500 mt-0.5">
                                                {getCurrentLocale() === "zh-CN" ? m.description : (m.description_en ?? m.description)}
                                            </p>
                                        </div>
                                        <a
                                            href={m.pricing_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            onClick={(e) => e.stopPropagation()}
                                            className="text-primary-500 hover:text-primary-700 shrink-0"
                                            title={t("settings.view_pricing")}
                                        >
                                            <ExternalLink className="w-4 h-4"/>
                                        </a>
                                    </label>
                                ))}
                            </div>
                        </div>

                        {/* 自定义 Base URL（高级） */}
                        <details className="group">
                            <summary className="text-sm text-slate-500 cursor-pointer hover:text-slate-700">
                                {t("settings.advanced")}
                            </summary>
                            <div className="mt-3">
                                <label className="block text-sm font-medium text-slate-700 mb-1">
                                    {t("settings.base_url")}
                                </label>
                                <input
                                    type="text"
                                    value={baseUrl}
                                    onChange={(e) => setBaseUrl(e.target.value)}
                                    onBlur={handleBlurSave}
                                    placeholder={t("settings.base_url_placeholder")}
                                    className="w-full px-4 py-2.5 border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                                />
                                <p className="text-xs text-slate-400 mt-1">
                                    {t("settings.base_url_hint")}
                                </p>
                            </div>
                        </details>

                        {/* ── 通用 ── */}
                        {isDesktop && (
                        <div className="space-y-4">
                            <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
                                {t("settings.general")}
                            </h3>

                            {/* 开机自启 */}
                            <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
                                <div className="flex items-center gap-3">
                                    <Power className="w-5 h-5 text-slate-500"/>
                                    <div>
                                        <p className="text-sm font-medium text-slate-700">{t("settings.autostart")}</p>
                                        <p className="text-xs text-slate-400">{t("settings.autostart_desc")}</p>
                                    </div>
                                </div>
                                <button
                                    onClick={async () => {
                                        setAutostartLoading(true);
                                        try {
                                            const res = await apiSetAutostart(!autostart);
                                            setAutostartState(res.enabled);
                                        } catch (err) {
                                            setError(extractErrorMessage(err));
                                        } finally {
                                            setAutostartLoading(false);
                                        }
                                    }}
                                    disabled={autostartLoading}
                                    className={`relative w-11 h-6 rounded-full transition-colors ${
                                        autostart ? "bg-primary-600" : "bg-slate-300"
                                    }`}
                                >
                                    <span
                                        className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                                            autostart ? "translate-x-5" : ""
                                        }`}
                                    />
                                </button>
                            </div>

                            {/* 关闭窗口行为 */}
                            <div className="p-4 bg-slate-50 rounded-xl space-y-3">
                                <p className="text-sm font-medium text-slate-700">{t("settings.close_behavior")}</p>
                                <div className="flex gap-2">
                                    <button
                                        type="button"
                                        onClick={async () => {
                                            try {
                                                await apiSetCloseBehavior("minimize_to_tray");
                                                setCloseBehaviorState("minimize_to_tray");
                                            } catch (err) { setError(extractErrorMessage(err)); }
                                        }}
                                        className={`flex-1 flex items-center justify-center gap-2 px-3 py-2.5 text-sm font-medium rounded-xl border transition-all ${
                                            closeBehavior === "minimize_to_tray"
                                                ? "border-primary-500 bg-primary-50 text-primary-700"
                                                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                                        }`}
                                    >
                                        <Minimize2 className="w-4 h-4"/>
                                        {t("settings.close_minimize")}
                                    </button>
                                    <button
                                        type="button"
                                        onClick={async () => {
                                            try {
                                                await apiSetCloseBehavior("exit");
                                                setCloseBehaviorState("exit");
                                            } catch (err) { setError(extractErrorMessage(err)); }
                                        }}
                                        className={`flex-1 flex items-center justify-center gap-2 px-3 py-2.5 text-sm font-medium rounded-xl border transition-all ${
                                            closeBehavior === "exit"
                                                ? "border-primary-500 bg-primary-50 text-primary-700"
                                                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                                        }`}
                                    >
                                        <LogOut className="w-4 h-4"/>
                                        {t("settings.close_exit")}
                                    </button>
                                </div>
                            </div>

                            {/* 重置窗口大小 */}
                            <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
                                <div className="flex items-center gap-3">
                                    <RotateCcw className="w-5 h-5 text-slate-500"/>
                                    <div>
                                        <p className="text-sm font-medium text-slate-700">{t("settings.reset_window")}</p>
                                        <p className="text-xs text-slate-400">{t("settings.reset_window_desc")}</p>
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    onClick={async () => {
                                        try {
                                            const res = await apiResetWindow();
                                            setResetMsg(res.message);
                                            setTimeout(() => setResetMsg(null), 3000);
                                        } catch (err) { setError(extractErrorMessage(err)); }
                                    }}
                                    className="px-3 py-1.5 text-sm border border-slate-300 rounded-lg hover:bg-white transition-colors"
                                >
                                    {t("settings.reset_window_btn")}
                                </button>
                            </div>
                            {resetMsg && (
                                <p className="text-xs text-emerald-600 flex items-center gap-1">
                                    <CheckCircle className="w-3.5 h-3.5"/> {resetMsg}
                                </p>
                            )}

                            {/* 自动更新 */}
                            <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
                                <div className="flex items-center gap-3">
                                    <RefreshCw className="w-5 h-5 text-slate-500"/>
                                    <div>
                                        <p className="text-sm font-medium text-slate-700">{t("settings.auto_update")}</p>
                                        <p className="text-xs text-slate-400">{t("settings.auto_update_desc")}</p>
                                    </div>
                                </div>
                                <button
                                    onClick={async () => {
                                        try {
                                            const res = await apiSetAutoUpdate(!autoUpdate);
                                            setAutoUpdateState(res.enabled);
                                        } catch (err) { setError(extractErrorMessage(err)); }
                                    }}
                                    className={`relative w-11 h-6 rounded-full transition-colors ${
                                        autoUpdate ? "bg-primary-600" : "bg-slate-300"
                                    }`}
                                >
                                    <span
                                        className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                                            autoUpdate ? "translate-x-5" : ""
                                        }`}
                                    />
                                </button>
                            </div>
                        </div>
                        )}

                        {/* 界面语言 */}
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-2">
                                {t("settings.language")}
                            </label>
                            <div className="flex gap-2">
                                {LOCALE_OPTIONS.map((opt) => (
                                    <button
                                        key={opt.value}
                                        type="button"
                                        onClick={() => setLanguage(opt.value)}
                                        className={`flex-1 px-4 py-2.5 text-sm font-medium rounded-xl border transition-all ${
                                            language === opt.value
                                                ? "border-primary-500 bg-primary-50 text-primary-700"
                                                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                                        }`}
                                    >
                                        {opt.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* 错误/成功提示 */}
                        {error && (
                            <div
                                className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 flex items-center gap-2">
                                <AlertCircle className="w-4 h-4 shrink-0"/>
                                {error}
                            </div>
                        )}
                        {saved && (
                            <div
                                className="bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm rounded-xl px-4 py-3 flex items-center gap-2">
                                <CheckCircle className="w-4 h-4 shrink-0"/>
                                {t("settings.saved")}
                            </div>
                        )}

                    {/* 关于 & 版本 */}
                    <div className="p-4 bg-slate-50 rounded-xl space-y-3">
                        <div className="flex items-center gap-2">
                            <Info className="w-4 h-4 text-slate-500"/>
                            <span className="text-sm font-medium text-slate-700">{t("settings.about")}</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="text-sm text-slate-500">
                                <span>{t("settings.update_current")}: </span>
                                <span className="font-mono font-medium text-slate-700">
                                    {versionInfo?.current ?? (appVersion || "...")}
                                </span>
                            </div>
                            {/* 检查更新（桌面专属） */}
                            {isDesktop && (
                            <button
                                onClick={async () => {
                                    setUpdateLoading(true);
                                    setUpdateError(null);
                                    try {
                                        const info = await checkUpdate();
                                        setVersionInfo(info);
                                    } catch {
                                        setUpdateError(t("settings.update_error"));
                                    } finally {
                                        setUpdateLoading(false);
                                    }
                                }}
                                disabled={updateLoading}
                                className="px-3 py-1.5 text-sm border border-slate-300 rounded-lg hover:bg-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
                            >
                                {updateLoading ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin"/>
                                ) : (
                                    <RefreshCw className="w-3.5 h-3.5"/>
                                )}
                                {updateLoading ? t("settings.update_checking") : t("settings.update")}
                            </button>
                            )}
                        </div>
                        {versionInfo && !versionInfo.has_update && (
                            <p className="text-xs text-emerald-600 flex items-center gap-1">
                                <CheckCircle className="w-3.5 h-3.5"/>
                                {t("settings.update_latest")}
                            </p>
                        )}
                        {versionInfo?.has_update && (
                            <div className="bg-primary-50 rounded-lg px-3 py-2 space-y-2">
                                <div className="flex items-center justify-between">
                                    <p className="text-sm text-primary-700">
                                        {t("settings.update_available").replace("{version}", versionInfo.latest ?? "")}
                                    </p>
                                    <button
                                        onClick={async () => {
                                            await triggerUpdateDownload();
                                            const s = await getUpdateStatus();
                                            setUpdateStatus(s);
                                        }}
                                        disabled={updateStatus?.status === "downloading"}
                                        className="text-sm text-primary-600 hover:text-primary-800 font-medium flex items-center gap-1 disabled:opacity-50"
                                    >
                                        {updateStatus?.status === "downloading" ? (
                                            <Loader2 className="w-3.5 h-3.5 animate-spin"/>
                                        ) : (
                                            <Download className="w-3.5 h-3.5"/>
                                        )}
                                        {updateStatus?.status === "downloading" ? `${updateStatus.progress}%` : t("settings.update_go")}
                                    </button>
                                </div>
                                {updateStatus?.status === "ready" && (
                                    <p className="text-xs text-emerald-600 flex items-center gap-1">
                                        <CheckCircle className="w-3.5 h-3.5"/>
                                        {updateStatus.message}
                                    </p>
                                )}
                            </div>
                        )}
                        {updateError && (
                            <p className="text-xs text-red-500">{updateError}</p>
                        )}
                    </div>

                    {/* 自动保存状态指示 */}
                    {saving && (
                        <div className="flex items-center gap-2 text-xs text-slate-400 justify-end pt-1">
                            <Loader2 className="w-3.5 h-3.5 animate-spin"/>
                            {t("settings.saving")}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
