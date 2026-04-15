/**
 * 轻量级 i18n 国际化模块。
 *
 * 支持语言：zh-CN（中文，默认）、en（英文）、sr（塞尔维亚语）
 * 用法：const t = useT(); t("upload")
 */

import { useState, useCallback, useEffect } from "react";

export type Locale = "zh-CN" | "en" | "sr";

const messages: Record<Locale, Record<string, string>> = {
  "zh-CN": {
    "app.title": "DocAI Pipeline",
    "app.subtitle": "报关单自动识别与智能归档系统",
    "app.version": "v0.2",
    "nav.dashboard": "数据汇总",
    "nav.history": "处理历史",
    "nav.settings": "设置",
    "step.upload": "上传",
    "step.processing": "识别",
    "step.review": "复核",
    "step.done": "完成",
    "upload.title": "上传文档",
    "upload.hint": "拖放文件到此处，或点击选择",
    "upload.supported": "支持 PDF、JPG、PNG、TIFF 格式",
    "upload.select_type": "选择文档类型",
    "upload.start": "开始识别",
    "upload.template": "选择 Excel 模板（可选）",
    "review.title": "识别结果复核",
    "review.fill": "填充 Excel",
    "review.download": "下载",
    "review.retry": "重新处理",
    "done.title": "处理完成",
    "done.rows": "写入行数",
    "done.download": "下载 Excel",
    "done.new": "处理新文档",
    "error.backend_offline": "后端未连接",
    "error.no_api_key": "请先设置 OpenAI API Key",
    "setup.welcome": "欢迎使用 DocAI Pipeline！",
    "setup.hint": "首次使用前，请先设置 OpenAI API Key 以启用文档识别功能。",
    "setup.go_settings": "前往设置",
    "doc_type.auto": "自动识别",
    "doc_type.customs": "进口单据（报关/税款/发票）",
    "doc_type.log_measurement": "原木检尺单",
    "doc_type.log_output": "原木领用出库表",
    "doc_type.soak_pool": "刨切木方入池表",
    "doc_type.slicing": "刨切木方上机表",
    "doc_type.packing": "表板打包报表",
    "history.title": "处理历史",
    "history.empty": "暂无处理历史",
    "history.empty_hint": "上传并处理文档后，记录将自动保存在这里",
    "history.search": "搜索文件名...",
    "history.all_types": "全部类型",
    "history.load": "加载到复核",
    "dashboard.title": "数据汇总看板",
    "dashboard.overview": "总览",
    "dashboard.import": "进口采购",
    "dashboard.log": "原木进销存",
    "dashboard.factory": "工厂加工",
    "dashboard.empty": "暂无数据",
    "dashboard.empty_hint": "处理文档后，汇总数据将自动更新",
    "footer.powered": "Terra Drvo d.o.o. · 驱动自",
  },
  en: {
    "app.title": "DocAI Pipeline",
    "app.subtitle": "Automated Document Recognition & Smart Filing",
    "app.version": "v0.2",
    "nav.dashboard": "Dashboard",
    "nav.history": "History",
    "nav.settings": "Settings",
    "step.upload": "Upload",
    "step.processing": "Process",
    "step.review": "Review",
    "step.done": "Done",
    "upload.title": "Upload Document",
    "upload.hint": "Drop file here, or click to select",
    "upload.supported": "PDF, JPG, PNG, TIFF supported",
    "upload.select_type": "Select document type",
    "upload.start": "Start Processing",
    "upload.template": "Select Excel template (optional)",
    "review.title": "Review Results",
    "review.fill": "Fill Excel",
    "review.download": "Download",
    "review.retry": "Reprocess",
    "done.title": "Complete",
    "done.rows": "Rows Written",
    "done.download": "Download Excel",
    "done.new": "Process New Document",
    "error.backend_offline": "Backend offline",
    "error.no_api_key": "Please set OpenAI API Key first",
    "setup.welcome": "Welcome to DocAI Pipeline!",
    "setup.hint": "Please set your OpenAI API Key to enable document recognition.",
    "setup.go_settings": "Go to Settings",
    "doc_type.auto": "Auto Detect",
    "doc_type.customs": "Import Documents (Customs/Tax/Invoice)",
    "doc_type.log_measurement": "Log Measurement Sheet",
    "doc_type.log_output": "Log Output Sheet",
    "doc_type.soak_pool": "Soak Pool Sheet",
    "doc_type.slicing": "Slicing Sheet",
    "doc_type.packing": "Packing Sheet",
    "history.title": "Processing History",
    "history.empty": "No history yet",
    "history.empty_hint": "Records will be saved here after processing documents",
    "history.search": "Search filename...",
    "history.all_types": "All Types",
    "history.load": "Load to Review",
    "dashboard.title": "Data Dashboard",
    "dashboard.overview": "Overview",
    "dashboard.import": "Import & Purchase",
    "dashboard.log": "Log Inventory",
    "dashboard.factory": "Factory Processing",
    "dashboard.empty": "No data",
    "dashboard.empty_hint": "Dashboard updates automatically after processing",
    "footer.powered": "Terra Drvo d.o.o. · Powered by",
  },
  sr: {
    "app.title": "DocAI Pipeline",
    "app.subtitle": "Automatsko prepoznavanje i arhiviranje dokumenata",
    "app.version": "v0.2",
    "nav.dashboard": "Pregled",
    "nav.history": "Istorija",
    "nav.settings": "Podešavanja",
    "step.upload": "Otpremi",
    "step.processing": "Obrada",
    "step.review": "Pregled",
    "step.done": "Gotovo",
    "upload.title": "Otpremi dokument",
    "upload.hint": "Prevucite datoteku ovde ili kliknite za izbor",
    "upload.supported": "PDF, JPG, PNG, TIFF formati",
    "upload.select_type": "Izaberite tip dokumenta",
    "upload.start": "Započni obradu",
    "upload.template": "Izaberite Excel šablon (opciono)",
    "review.title": "Pregled rezultata",
    "review.fill": "Popuni Excel",
    "review.download": "Preuzmi",
    "review.retry": "Ponovi obradu",
    "done.title": "Završeno",
    "done.rows": "Upisanih redova",
    "done.download": "Preuzmi Excel",
    "done.new": "Obradi novi dokument",
    "error.backend_offline": "Server nije dostupan",
    "error.no_api_key": "Molimo prvo podesite OpenAI API ključ",
    "setup.welcome": "Dobrodošli u DocAI Pipeline!",
    "setup.hint": "Podesite OpenAI API ključ da biste omogućili prepoznavanje.",
    "setup.go_settings": "Idi na podešavanja",
    "doc_type.auto": "Automatski",
    "doc_type.customs": "Uvozni dokumenti (carina/porez/faktura)",
    "doc_type.log_measurement": "Merenje trupaca",
    "doc_type.log_output": "Izdavanje trupaca",
    "doc_type.soak_pool": "Tabela potapanja",
    "doc_type.slicing": "Tabela rezanja",
    "doc_type.packing": "Tabela pakovanja",
    "history.title": "Istorija obrade",
    "history.empty": "Nema istorije",
    "history.empty_hint": "Zapisi će biti sačuvani ovde nakon obrade",
    "history.search": "Pretraži...",
    "history.all_types": "Svi tipovi",
    "history.load": "Učitaj za pregled",
    "dashboard.title": "Pregled podataka",
    "dashboard.overview": "Pregled",
    "dashboard.import": "Uvoz i nabavka",
    "dashboard.log": "Inventar trupaca",
    "dashboard.factory": "Fabrika",
    "dashboard.empty": "Nema podataka",
    "dashboard.empty_hint": "Podaci se ažuriraju nakon obrade",
    "footer.powered": "Terra Drvo d.o.o. · Pokreće",
  },
};

// 全局当前语言
let _currentLocale: Locale = "zh-CN";
const _listeners: Set<() => void> = new Set();

export function getCurrentLocale(): Locale {
  return _currentLocale;
}

export function setLocale(locale: Locale): void {
  if (locale === _currentLocale) return;
  _currentLocale = locale;
  _listeners.forEach((fn) => fn());
}

/**
 * 翻译函数：根据当前语言返回对应文本。
 * 找不到时回退到 zh-CN，再找不到返回 key 本身。
 */
export function t(key: string): string {
  return messages[_currentLocale]?.[key]
    ?? messages["zh-CN"]?.[key]
    ?? key;
}

/**
 * React Hook：获取翻译函数，语言切换时自动刷新。
 */
export function useT(): (key: string) => string {
  const [, setTick] = useState(0);

  useEffect(() => {
    const listener = () => setTick((n) => n + 1);
    _listeners.add(listener);
    return () => { _listeners.delete(listener); };
  }, []);

  return useCallback((key: string) => t(key), [_currentLocale]);
}

export const LOCALE_OPTIONS: { value: Locale; label: string }[] = [
  { value: "zh-CN", label: "简体中文" },
  { value: "en", label: "English" },
  { value: "sr", label: "Srpski" },
];
