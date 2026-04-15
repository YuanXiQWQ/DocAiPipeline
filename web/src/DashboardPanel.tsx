import React, { useState, useEffect } from "react";
import {
  BarChart3,
  X,
  Truck,
  TreePine,
  Package,
  Scissors,
  ArrowDownCircle,
  ArrowUpCircle,
  Loader2,
} from "lucide-react";
import {
  getSummary,
  extractErrorMessage,
  type OverallSummary,
} from "./api";

interface DashboardPanelProps {
  onClose: () => void;
}

function StatCard({
  icon,
  label,
  value,
  unit,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  unit?: string;
  color: string;
}) {
  return (
    <div className={`rounded-xl border p-4 ${color}`}>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-sm font-medium text-gray-600">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900">
        {typeof value === "number" ? value.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) : value}
        {unit && <span className="text-sm font-normal text-gray-500 ml-1">{unit}</span>}
      </p>
    </div>
  );
}

export default function DashboardPanel({ onClose }: DashboardPanelProps) {
  const [data, setData] = useState<OverallSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getSummary()
      .then(setData)
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <BarChart3 className="w-6 h-6 text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900">数据汇总看板</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : error ? (
            <div className="text-center py-20 text-red-500">{error}</div>
          ) : data ? (
            <div className="space-y-8">
              {/* 总览 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
                  总览
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <StatCard
                    icon={<BarChart3 className="w-5 h-5 text-blue-500" />}
                    label="已处理文档"
                    value={data.total_documents_processed}
                    unit="份"
                    color="bg-blue-50 border-blue-200"
                  />
                  <StatCard
                    icon={<BarChart3 className="w-5 h-5 text-indigo-500" />}
                    label="已处理页数"
                    value={data.total_pages_processed}
                    unit="页"
                    color="bg-indigo-50 border-indigo-200"
                  />
                  <StatCard
                    icon={<ArrowDownCircle className="w-5 h-5 text-emerald-500" />}
                    label="原木入库"
                    value={data.log_summary.total_inbound_m3}
                    unit="m³"
                    color="bg-emerald-50 border-emerald-200"
                  />
                  <StatCard
                    icon={<ArrowUpCircle className="w-5 h-5 text-amber-500" />}
                    label="原木出库"
                    value={data.log_summary.total_outbound_m3}
                    unit="m³"
                    color="bg-amber-50 border-amber-200"
                  />
                </div>
              </div>

              {/* 进口采购 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                  <Truck className="w-4 h-4" />
                  进口采购
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <StatCard
                    icon={<Truck className="w-5 h-5 text-sky-500" />}
                    label="批次数"
                    value={data.import_summary.total_batches}
                    color="bg-sky-50 border-sky-200"
                  />
                  <StatCard
                    icon={<Truck className="w-5 h-5 text-sky-500" />}
                    label="发票数"
                    value={data.import_summary.total_invoices}
                    color="bg-sky-50 border-sky-200"
                  />
                  <StatCard
                    icon={<Truck className="w-5 h-5 text-sky-500" />}
                    label="总金额"
                    value={data.import_summary.total_amount_eur}
                    unit="EUR"
                    color="bg-sky-50 border-sky-200"
                  />
                  <StatCard
                    icon={<Truck className="w-5 h-5 text-sky-500" />}
                    label="总体积"
                    value={data.import_summary.total_volume_m3}
                    unit="m³"
                    color="bg-sky-50 border-sky-200"
                  />
                </div>
                {Object.keys(data.import_summary.suppliers).length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {Object.entries(data.import_summary.suppliers).map(([name, count]) => (
                      <span
                        key={name}
                        className="px-2.5 py-1 bg-sky-100 text-sky-800 rounded-full text-xs font-medium"
                      >
                        {name} ({count})
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* 原木进销存 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                  <TreePine className="w-4 h-4" />
                  原木进销存
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <StatCard
                    icon={<ArrowDownCircle className="w-5 h-5 text-emerald-500" />}
                    label="入库根数"
                    value={data.log_summary.total_inbound_logs}
                    unit="根"
                    color="bg-emerald-50 border-emerald-200"
                  />
                  <StatCard
                    icon={<ArrowDownCircle className="w-5 h-5 text-emerald-500" />}
                    label="入库体积"
                    value={data.log_summary.total_inbound_m3}
                    unit="m³"
                    color="bg-emerald-50 border-emerald-200"
                  />
                  <StatCard
                    icon={<ArrowUpCircle className="w-5 h-5 text-orange-500" />}
                    label="出库根数"
                    value={data.log_summary.total_outbound_logs}
                    unit="根"
                    color="bg-orange-50 border-orange-200"
                  />
                  <StatCard
                    icon={<ArrowUpCircle className="w-5 h-5 text-orange-500" />}
                    label="出库体积"
                    value={data.log_summary.total_outbound_m3}
                    unit="m³"
                    color="bg-orange-50 border-orange-200"
                  />
                </div>
                {/* 库存概览 */}
                {(data.log_summary.total_inbound_m3 > 0 || data.log_summary.total_outbound_m3 > 0) && (
                  <div className="mt-3 p-3 bg-gray-50 rounded-lg text-sm">
                    <span className="text-gray-600">当前库存（入-出）：</span>
                    <span className="font-bold text-gray-900 ml-1">
                      {(data.log_summary.total_inbound_m3 - data.log_summary.total_outbound_m3).toFixed(2)} m³
                    </span>
                    <span className="text-gray-500 ml-2">
                      ({data.log_summary.total_inbound_logs - data.log_summary.total_outbound_logs} 根)
                    </span>
                  </div>
                )}
              </div>

              {/* 工厂加工 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                  <Scissors className="w-4 h-4" />
                  工厂加工
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <StatCard
                    icon={<Package className="w-5 h-5 text-violet-500" />}
                    label="入池"
                    value={`${data.factory_summary.soak_pool_logs} 根`}
                    unit={data.factory_summary.soak_pool_m3 > 0 ? `/ ${data.factory_summary.soak_pool_m3.toFixed(2)} m³` : undefined}
                    color="bg-violet-50 border-violet-200"
                  />
                  <StatCard
                    icon={<Scissors className="w-5 h-5 text-rose-500" />}
                    label="刨切上机"
                    value={`${data.factory_summary.slicing_logs} 根`}
                    unit={data.factory_summary.slicing_output_m2 > 0 ? `/ ${data.factory_summary.slicing_output_m2.toFixed(2)} m²` : undefined}
                    color="bg-rose-50 border-rose-200"
                  />
                  <StatCard
                    icon={<Package className="w-5 h-5 text-teal-500" />}
                    label="打包"
                    value={`${data.factory_summary.packing_packages} 包`}
                    unit={`/ ${data.factory_summary.packing_pieces} 片 / ${data.factory_summary.packing_area_m2.toFixed(2)} m²`}
                    color="bg-teal-50 border-teal-200"
                  />
                </div>
              </div>

              {/* 空数据提示 */}
              {data.total_documents_processed === 0 && (
                <div className="text-center py-10 text-gray-400">
                  <BarChart3 className="w-12 h-12 mx-auto mb-3" />
                  <p className="text-lg">暂无数据</p>
                  <p className="text-sm">处理文档后，汇总数据将自动更新</p>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
