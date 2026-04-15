/**
 * 轻量级 i18n 国际化模块。
 *
 * 翻译文本存放在 lang/*.json 中，每种语言一个文件。
 * 支持语言：zh-CN（中文，默认）、en（英文）、sr（塞尔维亚语）。
 * 用法：const t = useT(); t("upload.hint")
 */

import { useState, useCallback, useEffect } from "react";

import zhCN from "./lang/zh-CN.json";
import en from "./lang/en.json";
import sr from "./lang/sr.json";

export type Locale = "zh-CN" | "en" | "sr";

/** 各语言翻译表，由 lang/*.json 静态导入 */
const messages: Record<Locale, Record<string, string>> = {
  "zh-CN": zhCN,
  en,
  sr,
};

/** 当前激活的语言 */
let _currentLocale: Locale = "zh-CN";

/** 语言变更监听器集合 */
const _listeners: Set<() => void> = new Set();

export function getCurrentLocale(): Locale {
  return _currentLocale;
}

/** 切换当前语言，并通知所有监听器刷新 */
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
 * React Hook：返回翻译函数 t()，语言切换时自动触发组件重渲染。
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

/** 语言选择器选项列表 */
export const LOCALE_OPTIONS: { value: Locale; label: string }[] = [
  { value: "zh-CN", label: "简体中文" },
  { value: "en", label: "English" },
  { value: "sr", label: "Srpski" },
];
