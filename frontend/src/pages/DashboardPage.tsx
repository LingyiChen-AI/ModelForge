import { useEffect, useState } from "react";
import { Database, Boxes, Layers, Cpu, BarChart3, Rocket, RefreshCw, type LucideIcon } from "lucide-react";
import { getStats, getCharts, type Stats, type Charts } from "../api/client";
import { Button, PageHeader } from "../ui";
import { Donut, BarList, type Seg } from "../components/charts";
import { navigate } from "../router";

type Tone = "blue" | "violet" | "cyan" | "amber" | "green" | "brand" | "indigo";
type StatCard = { key: string; label: string; icon: LucideIcon; to: string; tone: Tone };

const CARDS: StatCard[] = [
  { key: "datasets", label: "数据集", icon: Database, to: "/datasets", tone: "blue" },
  { key: "models", label: "模型", icon: Boxes, to: "/models", tone: "violet" },
  { key: "model_versions", label: "模型版本", icon: Layers, to: "/models", tone: "cyan" },
  { key: "training_jobs", label: "训练任务", icon: Cpu, to: "/training", tone: "amber" },
  { key: "eval_runs", label: "模型测试", icon: BarChart3, to: "/eval", tone: "indigo" },
  { key: "deployments", label: "部署", icon: Rocket, to: "/deploy", tone: "brand" },
];

const TONE: Record<Tone, string> = {
  blue: "bg-blue-50 text-blue-600", violet: "bg-violet-50 text-violet-600",
  cyan: "bg-cyan-50 text-cyan-600", amber: "bg-amber-50 text-amber-600",
  green: "bg-emerald-50 text-emerald-600", brand: "bg-brand-50 text-brand-600",
  indigo: "bg-indigo-50 text-indigo-600",
};

type Conf = { key: string; label: string; color: string };
const STATUS_CONF: Conf[] = [
  { key: "succeeded", label: "成功", color: "#10b981" }, { key: "running", label: "运行中", color: "#3b82f6" },
  { key: "pending", label: "等待", color: "#f59e0b" }, { key: "failed", label: "失败", color: "#ef4444" },
];
const TASK_CONF: Conf[] = [
  { key: "classification", label: "分类", color: "#3b82f6" }, { key: "ner", label: "序列标注", color: "#8b5cf6" },
  { key: "pair", label: "句对", color: "#06b6d4" }, { key: "embedding", label: "向量", color: "#f59e0b" },
];
const KIND_CONF: Conf[] = [
  { key: "train", label: "训练集", color: "#3b82f6" }, { key: "eval", label: "评估集", color: "#10b981" },
  { key: "test", label: "测试集", color: "#8b5cf6" },
];
const DEPLOY_CONF: Conf[] = [
  { key: "running", label: "运行中", color: "#10b981" }, { key: "stopped", label: "已停止", color: "#94a3b8" },
  { key: "failed", label: "失败", color: "#ef4444" }, { key: "pending", label: "等待", color: "#f59e0b" },
];

function toSegs(rec: Record<string, number> | undefined, conf: Conf[]): Seg[] {
  if (!rec) return [];
  const known = conf.filter(c => c.key in rec).map(c => ({ label: c.label, value: rec[c.key], color: c.color }));
  const extra = Object.keys(rec).filter(k => !conf.some(c => c.key === k))
    .map(k => ({ label: k, value: rec[k], color: "#94a3b8" }));
  return [...known, ...extra].filter(s => s.value > 0);
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-5">
      <div className="mb-4 text-[14px] font-medium text-slate-700">{title}</div>
      {children}
    </div>
  );
}

export function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [charts, setCharts] = useState<Charts>({});
  const [error, setError] = useState(false);
  const load = () => {
    setError(false); setStats(null);
    getStats().then(setStats).catch(() => setError(true));
    getCharts().then(setCharts).catch(() => {});
  };
  useEffect(load, []);
  const cards = CARDS.filter(c => stats && c.key in stats);

  return (
    <>
      <PageHeader title="概览" subtitle="你权限范围内的核心数据统计与报表。" />

      {error ? (
        <div className="card flex flex-col items-center gap-3 p-8 text-center">
          <p className="text-[13px] text-slate-500">统计加载失败,请重试。</p>
          <Button variant="subtle" onClick={load}><RefreshCw size={14} /> 重试</Button>
        </div>
      ) : stats === null ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => <div key={i} className="card h-[104px] animate-pulse bg-slate-50" />)}
        </div>
      ) : cards.length === 0 ? (
        <div className="card p-8 text-center text-[13px] text-slate-400">暂无可展示的统计(没有相关读权限)。</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {cards.map(c => {
              const Icon = c.icon;
              return (
                <button
                  key={c.key}
                  onClick={() => navigate(c.to)}
                  className="card flex flex-col gap-3 p-5 text-left transition hover:shadow-md hover:ring-1 hover:ring-brand-200 cursor-pointer"
                >
                  <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${TONE[c.tone]}`}><Icon size={20} /></div>
                  <div>
                    <div className="tnum text-[28px] font-semibold leading-none text-slate-900">{stats[c.key]}</div>
                    <div className="mt-1.5 text-[12.5px] text-slate-500">{c.label}</div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {charts.jobs_by_status && <ChartCard title="训练任务状态"><Donut data={toSegs(charts.jobs_by_status, STATUS_CONF)} /></ChartCard>}
            {charts.deployments_by_status && <ChartCard title="部署状态"><Donut data={toSegs(charts.deployments_by_status, DEPLOY_CONF)} /></ChartCard>}
            {charts.versions_by_task && <ChartCard title="模型版本 · 任务分布"><BarList data={toSegs(charts.versions_by_task, TASK_CONF)} /></ChartCard>}
            {charts.datasets_by_kind && <ChartCard title="数据集 · 类型分布"><BarList data={toSegs(charts.datasets_by_kind, KIND_CONF)} /></ChartCard>}
          </div>
        </>
      )}
    </>
  );
}
