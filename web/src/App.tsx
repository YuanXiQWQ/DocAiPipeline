import { useState, useCallback, useRef } from "react";
import {
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
  Download,
  Loader2,
  TreePine,
  Truck,
  Package,
  Scissors,
  ClipboardList,
} from "lucide-react";
import {
  processDocument,
  fillExcel,
  DOC_TYPE_LABELS,
  type ProcessResult,
  type FillResult,
} from "./api";

/* 文档类型图标映射 */
const DOC_ICONS: Record<string, React.ReactNode> = {
  customs: <Truck className="w-5 h-5" />,
  log_measurement: <TreePine className="w-5 h-5" />,
  log_output: <ClipboardList className="w-5 h-5" />,
  soak_pool: <Package className="w-5 h-5" />,
  slicing: <Scissors className="w-5 h-5" />,
  packing: <Package className="w-5 h-5" />,
};

type Step = "upload" | "processing" | "review" | "filling" | "done";

export default function App() {
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("auto");
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [fillResult, setFillResult] = useState<FillResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (f) setFile(f);
    },
    []
  );

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  }, []);

  const handleProcess = useCallback(async () => {
    if (!file) return;
    setStep("processing");
    setError(null);
    try {
      const res = await processDocument(file, docType);
      setResult(res);
      setStep("review");
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "处理失败";
      setError(msg);
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
      const msg =
        err instanceof Error ? err.message : "填充失败";
      setError(msg);
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
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      {/* 顶栏 */}
      <header className="bg-white/80 backdrop-blur border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TreePine className="w-7 h-7 text-emerald-600" />
            <h1 className="text-lg font-semibold text-slate-800">
              DocAI Pipeline
            </h1>
            <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">
              v0.2
            </span>
          </div>
          <p className="text-sm text-slate-500 hidden sm:block">
            报关单自动识别与智能归档系统
          </p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        {/* 步骤指示器 */}
        <div className="flex items-center justify-center gap-2 mb-10">
          {(
            [
              ["upload", "上传"],
              ["processing", "识别"],
              ["review", "复核"],
              ["done", "完成"],
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
                    <CheckCircle className="w-4 h-4" />
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
            <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-red-800 font-medium">处理出错</p>
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
                选择文档类型
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {Object.entries(DOC_TYPE_LABELS).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setDocType(key)}
                    className={`p-3 rounded-xl border text-left transition-all text-sm ${
                      docType === key
                        ? "border-blue-500 bg-blue-50 text-blue-700 shadow-sm"
                        : "border-slate-200 hover:border-slate-300 text-slate-600"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      {DOC_ICONS[key] || <FileText className="w-5 h-5" />}
                      <span className="font-medium">
                        {key === "auto" ? "自动" : key}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 leading-tight">
                      {label}
                    </p>
                  </button>
                ))}
              </div>
            </div>

            {/* 文件上传区 */}
            <div
              className="bg-white rounded-2xl shadow-sm border-2 border-dashed border-slate-300 hover:border-blue-400 transition-colors p-12 text-center cursor-pointer"
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
            >
              <input
                ref={inputRef}
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif"
                className="hidden"
                onChange={handleFileSelect}
              />
              <Upload className="w-12 h-12 text-slate-400 mx-auto mb-4" />
              <p className="text-slate-600 font-medium">
                点击上传或拖放文件到此处
              </p>
              <p className="text-sm text-slate-400 mt-2">
                支持 PDF / JPG / PNG / TIFF
              </p>
            </div>

            {/* 已选文件 */}
            {file && (
              <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileText className="w-8 h-8 text-blue-500" />
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
                  <Upload className="w-4 h-4" />
                  开始识别
                </button>
              </div>
            )}
          </div>
        )}

        {/* ===== 步骤 2: 处理中 ===== */}
        {(step === "processing" || step === "filling") && (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-16 text-center">
            <Loader2 className="w-12 h-12 text-blue-500 mx-auto mb-4 animate-spin" />
            <p className="text-lg text-slate-700 font-medium">
              {step === "processing" ? "正在识别文档…" : "正在填充 Excel…"}
            </p>
            <p className="text-sm text-slate-400 mt-2">
              VLM 正在分析文档内容，请稍候
            </p>
          </div>
        )}

        {/* ===== 步骤 3: 复核 ===== */}
        {step === "review" && result && (
          <div className="space-y-6">
            {/* 识别概览 */}
            <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-semibold text-slate-700">
                  识别结果
                </h2>
                <span className="px-3 py-1 bg-emerald-100 text-emerald-700 rounded-full text-sm font-medium flex items-center gap-1">
                  {DOC_ICONS[result.doc_type]}
                  {DOC_TYPE_LABELS[result.doc_type] || result.doc_type}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div className="bg-slate-50 rounded-xl p-4">
                  <p className="text-2xl font-bold text-slate-800">
                    {result.pages}
                  </p>
                  <p className="text-sm text-slate-500">页数</p>
                </div>
                <div className="bg-slate-50 rounded-xl p-4">
                  <p className="text-2xl font-bold text-slate-800">
                    {result.results.length}
                  </p>
                  <p className="text-sm text-slate-500">识别记录</p>
                </div>
                <div className="bg-slate-50 rounded-xl p-4">
                  <p className="text-2xl font-bold text-slate-800">
                    {result.warnings.length}
                  </p>
                  <p className="text-sm text-slate-500">警告</p>
                </div>
              </div>
            </div>

            {/* 警告列表 */}
            {result.warnings.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
                <h3 className="font-medium text-amber-800 mb-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  警告
                </h3>
                <ul className="space-y-1">
                  {result.warnings.map((w, i) => (
                    <li key={i} className="text-sm text-amber-700">
                      • {w}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 数据预览 */}
            <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
              <h3 className="font-medium text-slate-700 mb-3">数据预览</h3>
              <div className="max-h-96 overflow-auto">
                <pre className="text-xs text-slate-600 bg-slate-50 rounded-xl p-4 whitespace-pre-wrap">
                  {JSON.stringify(result.results, null, 2).slice(0, 5000)}
                  {JSON.stringify(result.results).length > 5000 && "\n..."}
                </pre>
              </div>
            </div>

            {/* Excel 模板上传（可选） */}
            <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
              <h3 className="font-medium text-slate-700 mb-3">
                Excel 模板（可选）
              </h3>
              <p className="text-sm text-slate-500 mb-3">
                上传目标 Excel 模板文件，或使用服务器已有模板
              </p>
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
                重新上传
              </button>
              <button
                onClick={handleFill}
                className="px-6 py-2.5 bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 transition-colors font-medium flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                填充 Excel
              </button>
            </div>
          </div>
        )}

        {/* ===== 步骤 4: 完成 ===== */}
        {step === "done" && fillResult && (
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-12 text-center">
            <CheckCircle className="w-16 h-16 text-emerald-500 mx-auto mb-6" />
            <h2 className="text-xl font-semibold text-slate-800 mb-2">
              处理完成
            </h2>
            <p className="text-slate-500 mb-6">
              已写入 <strong>{fillResult.rows_written}</strong> 行数据
            </p>
            <div className="flex gap-4 justify-center">
              <a
                href={fillResult.download_url}
                download
                className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-medium inline-flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                下载 Excel
              </a>
              <button
                onClick={handleReset}
                className="px-6 py-2.5 border border-slate-300 text-slate-600 rounded-xl hover:bg-slate-50 transition-colors"
              >
                处理下一个
              </button>
            </div>
          </div>
        )}
      </main>

      {/* 底栏 */}
      <footer className="text-center text-sm text-slate-400 py-6 mt-auto">
        Terra Drvo d.o.o. — DocAI Pipeline &copy; {new Date().getFullYear()}
      </footer>
    </div>
  );
}
