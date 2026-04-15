import { useState, useEffect, useCallback } from "react";
import {
  Settings as SettingsIcon,
  X,
  Eye,
  EyeOff,
  ExternalLink,
  Save,
  Loader2,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import {
  getSettings,
  updateSettings,
  extractErrorMessage,
  type UserSettings,
  type ModelInfo,
} from "./api";
import { getCurrentLocale, setLocale, LOCALE_OPTIONS, useT, type Locale } from "./i18n";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function SettingsPanel({ open, onClose }: Props) {
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

  // 加载设置
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setSaved(false);
    getSettings()
      .then((res) => {
        setCurrentSettings(res.settings);
        setModels(res.available_models);
        setSelectedModel(res.settings.openai_model);
        setBaseUrl(res.settings.openai_base_url);
        setApiKey(""); // 不回显真实 key
      })
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [open]);

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
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }, [apiKey, selectedModel, baseUrl, language]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl mx-4 max-h-[90vh] overflow-y-auto">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <SettingsIcon className="w-5 h-5 text-slate-600" />
            <h2 className="text-lg font-semibold text-slate-800">{t("settings.title")}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        {loading ? (
          <div className="p-12 text-center">
            <Loader2 className="w-8 h-8 text-blue-500 mx-auto animate-spin" />
            <p className="text-sm text-slate-500 mt-2">{t("settings.loading")}</p>
          </div>
        ) : (
          <div className="p-6 space-y-6">
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
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
              {!currentSettings?.openai_api_key_set && (
                <p className="text-xs text-amber-600 mt-1 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
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
                        <span className="text-xs bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
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
                      <ExternalLink className="w-4 h-4" />
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
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {error}
              </div>
            )}
            {saved && (
              <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm rounded-xl px-4 py-3 flex items-center gap-2">
                <CheckCircle className="w-4 h-4 shrink-0" />
                {t("settings.saved")}
              </div>
            )}

            {/* 保存按钮 */}
            <div className="flex justify-end pt-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-medium flex items-center gap-2 disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Save className="w-4 h-4" />
                )}
                {t("settings.save")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
