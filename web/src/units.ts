/**
 * 应用支持的单位常量与换算工具。
 * 设置页默认单位选项、看板筛选栏、明细行单位选择均引用此处，
 * 扩展单位时只需修改本文件。
 */

/* ---- 类型 ---- */

export type LengthUnit = "mm" | "cm" | "m" | "in" | "ft";
export type AreaUnit = "mm2" | "cm2" | "m2" | "in2" | "ft2";
export type VolumeUnit = "mm3" | "cm3" | "m3" | "in3" | "ft3";
export type CurrencyUnit = "EUR" | "USD" | "CNY" | "RSD" | "HRK" | "GBP" | "CAD";

export interface UnitConfig {
    length: LengthUnit;
    area: AreaUnit;
    volume: VolumeUnit;
    currency: CurrencyUnit;
}

/* ---- 可选值列表 ---- */

export const LENGTH_UNITS: LengthUnit[] = ["mm", "cm", "m", "in", "ft"];
export const AREA_UNITS: AreaUnit[] = ["mm2", "cm2", "m2", "in2", "ft2"];
export const VOLUME_UNITS: VolumeUnit[] = ["mm3", "cm3", "m3", "in3", "ft3"];
export const CURRENCY_UNITS: CurrencyUnit[] = ["EUR", "USD", "CNY", "RSD", "HRK", "GBP", "CAD"];

/* ---- 换算因子 ---- */

export const LENGTH_TO_M: Record<LengthUnit, number> = {mm: 0.001, cm: 0.01, m: 1, in: 0.0254, ft: 0.3048};
export const AREA_TO_M2: Record<AreaUnit, number> = {mm2: 1e-6, cm2: 1e-4, m2: 1, in2: 0.00064516, ft2: 0.092903};
export const VOL_TO_M3: Record<VolumeUnit, number> = {mm3: 1e-9, cm3: 1e-6, m3: 1, in3: 1.6387e-5, ft3: 0.0283168};

/** 所有货币 key 的小写集合，用于快速判断 */
export const CURRENCY_KEYS: Set<string> = new Set(CURRENCY_UNITS.map(c => c.toLowerCase()));

/* ---- 显示工具 ---- */

/** ASCII key → 显示用上标符号 */
const UNIT_LABEL: Record<string, string> = {
    mm2: "mm\u00b2", cm2: "cm\u00b2", m2: "m\u00b2", in2: "in\u00b2", ft2: "ft\u00b2",
    mm3: "mm\u00b3", cm3: "cm\u00b3", m3: "m\u00b3", in3: "in\u00b3", ft3: "ft\u00b3",
};

export function unitLabel(u: string): string {
    return UNIT_LABEL[u] ?? u;
}

/* ---- 默认值 ---- */

export const DEFAULT_UNITS: UnitConfig = {length: "m", area: "m2", volume: "m3", currency: "EUR"};
