import React, { useState, useEffect, useCallback } from "react";
import {
  Clock,
  FileText,
  Search,
  Trash2,
  ChevronLeft,
  ChevronRight,
  BarChart3,
  CheckCircle,
  X,
  Loader2,
} from "lucide-react";
import {
  listHistory,
  getHistoryStats,
  getHistoryDetail,
  deleteHistory,
  extractErrorMessage,
  DOC_TYPE_LABELS,
  type HistorySummary,
  type HistoryStats,
  type HistoryDetail,
} from "./api";

interface HistoryPanelProps {
  onClose: () => void;
  onLoadResult?: (detail: HistoryDetail) => void;
}

export default function HistoryPanel({ onClose, onLoadResult }: HistoryPanelProps) {
  const [records, setRecords] = useState<HistorySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<HistoryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [filterType, setFilterType] = useState<string>("");
  const [keyword, setKeyword] = useState("");
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const limit = 20;

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [listRes, statsRes] = await Promise.all([
        listHistory({
          doc_type: filterType || undefined,
          keyword: keyword || undefined,
          limit,
          offset,
        }),
        getHistoryStats(),
      ]);
      setRecords(listRes.records);
      setTotal(listRes.total);
      setStats(statsRes);
    } catch (err) {
      console.error("获取历史记录失败:", extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [filterType, keyword, offset]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此记录？")) return;
    try {
      await deleteHistory(id);
      fetchData();
    } catch (err) {
      alert("删除失败: " + extractErrorMessage(err));
    }
  };

  const handleDetail = async (id: string) => {
    setDetailLoading(true);
    try {
      const d = await getHistoryDetail(id);
      setDetail(d);
    } catch (err) {
      alert("获取详情失败: " + extractErrorMessage(err));
    } finally {
      setDetailLoading(false);
    }
  };

  const formatTime = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  // 详情视图
  if (detail) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
          {/* 标题栏 */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setDetail(null)}
                className="p-1.5 rounded-lg hover:bg-gray-100 transition"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <div>
                <h3 className="font-semibold text-gray-900">{detail.filename}</h3>
                <p className="text-sm text-gray-500">
                  {DOC_TYPE_LABELS[detail.doc_type] || detail.doc_type} · {formatTime(detail.timestamp)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {onLoadResult && (
                <button
                  onClick={() => {
                    onLoadResult(detail);
                    onClose();
                  }}
                  className="px-3 py-1.5 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition"
                >
                  加载到复核
                </button>
              )}
              <button
                onClick={() => setDetail(null)}
                className="p-1.5 rounded-lg hover:bg-gray-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* 内容 */}
          <div className="flex-1 overflow-y-auto p-6">
            {/* 元信息 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500">页数</p>
                <p className="text-lg font-semibold">{detail.pages}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500">识别记录数</p>
                <p className="text-lg font-semibold">{detail.record_count}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500">已填充</p>
                <p className="text-lg font-semibold">{detail.filled ? "✅ 是" : "否"}</p>
              </div>
              {detail.fill_filename && (
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500">Excel 文件</p>
                  <p className="text-sm font-medium truncate">{detail.fill_filename}</p>
                </div>
              )}
            </div>

            {/* 警告 */}
            {detail.warnings.length > 0 && (
              <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <p className="text-sm font-medium text-amber-800 mb-1">警告</p>
                {detail.warnings.map((w, i) => (
                  <p key={i} className="text-sm text-amber-700">{w}</p>
                ))}
              </div>
            )}

            {/* 识别结果 JSON */}
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">识别结果</p>
              <pre className="bg-gray-900 text-gray-100 rounded-lg p-4 text-xs overflow-x-auto max-h-96">
                {JSON.stringify(detail.results, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 主列表视图
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <Clock className="w-6 h-6 text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900">处理历史</h2>
            {stats && (
              <span className="text-sm text-gray-500">
                共 {stats.total_records} 条 · 近7天 {stats.recent_7_days} 条
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 统计卡片 */}
        {stats && stats.total_records > 0 && (
          <div className="px-6 py-3 border-b border-gray-100 bg-gray-50/50">
            <div className="flex gap-6 text-sm">
              <div className="flex items-center gap-1.5">
                <BarChart3 className="w-4 h-4 text-blue-500" />
                <span className="text-gray-600">总页数</span>
                <span className="font-semibold">{stats.total_pages_processed}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <FileText className="w-4 h-4 text-emerald-500" />
                <span className="text-gray-600">总记录</span>
                <span className="font-semibold">{stats.total_entries_extracted}</span>
              </div>
              {Object.entries(stats.by_doc_type).map(([type, count]) => (
                <div key={type} className="flex items-center gap-1">
                  <span className="text-gray-500">{DOC_TYPE_LABELS[type]?.split("（")[0] || type}</span>
                  <span className="font-medium text-gray-700">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 搜索与筛选 */}
        <div className="px-6 py-3 border-b border-gray-100 flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="搜索文件名..."
              value={keyword}
              onChange={(e) => {
                setKeyword(e.target.value);
                setOffset(0);
              }}
              className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <select
            value={filterType}
            onChange={(e) => {
              setFilterType(e.target.value);
              setOffset(0);
            }}
            className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="">全部类型</option>
            {Object.entries(DOC_TYPE_LABELS)
              .filter(([k]) => k !== "auto")
              .map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
          </select>
        </div>

        {/* 列表 */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : records.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-gray-400">
              <Clock className="w-12 h-12 mb-3" />
              <p className="text-lg">暂无处理历史</p>
              <p className="text-sm">上传并处理文档后，记录将自动保存在这里</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {records.map((r) => (
                <div
                  key={r.id}
                  className="px-6 py-3 hover:bg-gray-50 transition flex items-center gap-4 cursor-pointer"
                  onClick={() => handleDetail(r.id)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900 truncate">{r.filename}</span>
                      {r.filled && (
                        <CheckCircle className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500">
                      <span className="px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded">
                        {DOC_TYPE_LABELS[r.doc_type]?.split("（")[0] || r.doc_type}
                      </span>
                      <span>{r.pages} 页</span>
                      <span>{r.record_count} 条记录</span>
                      <span>{formatTime(r.timestamp)}</span>
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(r.id);
                    }}
                    className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500 transition"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 分页 */}
        {totalPages > 1 && (
          <div className="px-6 py-3 border-t border-gray-200 flex items-center justify-between text-sm">
            <span className="text-gray-500">
              第 {currentPage}/{totalPages} 页 · 共 {total} 条
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
                className="p-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={offset + limit >= total}
                className="p-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
