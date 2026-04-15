import {useState, useEffect, useCallback} from "react";
import {
    Settings as SettingsIcon,
    Eye,
    EyeOff,
    ExternalLink,
    Save,
    Loader2,
    CheckCircle,
    AlertCircle,
    RefreshCw,
    Power,
    Info,
} from "lucide-react";
import {
    getSettings,
    updateSettings,
    getAutostart,
    setAutostart as apiSetAutostart,
    checkUpdate,
    extractErrorMessage,
    type UserSettings,
    type ModelInfo,
    type VersionInfo,
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

    // 版本与更新
    const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
    const [updateLoading, setUpdateLoading] = useState(false);
    const [updateError, setUpdateError] = useState<string | null>(null);

    // 加载设置
    useEffect(() => {
        setLoading(true);
        setError(null);
        setSaved(false);
        Promise.all([
            getSettings(),
            getAutostart().catch(() => ({enabled: false})),
        ])
            .then(([res, autostartRes]) => {
                setCurrentSettings(res.settings);
                setModels(res.available_models);
                setSelectedModel(res.settings.openai_model);
                setBaseUrl(res.settings.openai_base_url);
                setApiKey("");
                setAutostartState(autostartRes.enabled);
            })
            .catch((err) => setError(extractErrorMessage(err)))
            .finally(() => setLoading(false));
    }, []);

    const handleSave = useCallback(async () => {
        setSaving(true);
        setError(null);
        setSaved(false);
        try {
            const body: Record<string, string> = {
                openai_model: selectedModel,
                openai_base_url: baseUrl,
                language: language,
            };
            // 只在用户输入了新 key 时才更新
            if (apiKey.trim()) {
                body.openai_api_key = apiKey.trim();
            }
            const res = await updateSettings(body);
            setCurrentSettings(res.settings);
            setApiKey("");
            // 同步前端语言
            setLocale(language);
            setSaved(true);
            onSettingsChange?.();
            setTimeout(() => setSaved(false), 3000);
        } catch (err) {
            setError(extractErrorMessage(err));
        } finally {
            setSaving(false);
        }
    }, [apiKey, selectedModel, baseUrl, language]);

    return (
        <div className="max-w-xl space-y-6">
            <div className="flex items-center gap-2 mb-2">
                <SettingsIcon className="w-6 h-6 text-slate-600"/>
                <h2 className="text-xl font-semibold text-slate-800">{t("settings.title")}</h2>
            </div>

            {loading ? (
                <div className="p-12 text-center">
                    <Loader2 className="w-8 h-8 text-blue-500 mx-auto animate-spin"/>
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
                                    placeholder={
                                        currentSettings?.openai_api_key_set
                                            ? t("settings.api_key_placeholder")
                                            : "sk-..."
                                    }
                                    className="w-full px-4 py-2.5 pr-10 border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
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
                                                ? "border-blue-500 bg-blue-50"
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
                                                {m.description}
                                            </p>
                                        </div>
                                        <a
                                            href={m.pricing_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            onClick={(e) => e.stopPropagation()}
                                            className="text-blue-500 hover:text-blue-700 shrink-0"
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
                                    placeholder={t("settings.base_url_placeholder")}
                                    className="w-full px-4 py-2.5 border border-slate-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                                />
                                <p className="text-xs text-slate-400 mt-1">
                                    {t("settings.base_url_hint")}
                                </p>
                            </div>
                        </details>

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
                                    autostart ? "bg-blue-600" : "bg-slate-300"
                                }`}
                            >
                                <span
                                    className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                                        autostart ? "translate-x-5" : ""
                                    }`}
                                />
                            </button>
                        </div>

                        {/* 界面语言 */}
                        <div>
                            <label className="block text-sm font-medium text-slate-700 mb-2">
                                {t("settings.language")}
                            </label>
                            <div className="flex gap-2">
                                {LOCALE_OPTIONS.map((opt) => (
                                    <button
                                        key={opt.value}
                                        onClick={() => setLanguage(opt.value)}
                                        className={`px-4 py-2 rounded-xl text-sm font-medium border transition-all ${
                                            language === opt.value
                                                ? "border-blue-500 bg-blue-50 text-blue-700"
                                                : "border-slate-200 text-slate-600 hover:border-slate-300"
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

                    {/* 关于 & 检查更新 */}
                    <div className="p-4 bg-slate-50 rounded-xl space-y-3">
                        <div className="flex items-center gap-2">
                            <Info className="w-4 h-4 text-slate-500"/>
                            <span className="text-sm font-medium text-slate-700">{t("settings.about")}</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="text-sm text-slate-500">
                                <span>{t("settings.update_current")}: </span>
                                <span className="font-mono font-medium text-slate-700">
                                    {versionInfo?.current ?? "..."}
                                </span>
                            </div>
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
                        </div>
                        {versionInfo && !versionInfo.has_update && (
                            <p className="text-xs text-emerald-600 flex items-center gap-1">
                                <CheckCircle className="w-3.5 h-3.5"/>
                                {t("settings.update_latest")}
                            </p>
                        )}
                        {versionInfo?.has_update && (
                            <div className="flex items-center justify-between bg-blue-50 rounded-lg px-3 py-2">
                                <p className="text-sm text-blue-700">
                                    {t("settings.update_available").replace("{version}", versionInfo.latest ?? "")}
                                </p>
                                <a
                                    href={versionInfo.release_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-sm text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                                >
                                    {t("settings.update_go")}
                                    <ExternalLink className="w-3.5 h-3.5"/>
                                </a>
                            </div>
                        )}
                        {updateError && (
                            <p className="text-xs text-red-500">{updateError}</p>
                        )}
                    </div>

                    {/* 保存按钮 */}
                    <div className="flex justify-end pt-2">
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-medium flex items-center gap-2 disabled:opacity-50"
                        >
                            {saving ? (
                                <Loader2 className="w-4 h-4 animate-spin"/>
                            ) : (
                                <Save className="w-4 h-4"/>
                            )}
                            {t("settings.save")}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
