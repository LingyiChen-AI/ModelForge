// Shared rendering for train/eval metric dicts: raw metric keys + percentage for rate metrics.
function fmtMetric(k: string, v: number | string): string {
  if (typeof v !== "number") return String(v);
  if (k === "badcase_fix_rate" || k.startsWith("recall@")) return (v * 100).toFixed(1) + "%";
  return Number.isInteger(v) ? String(v) : v.toFixed(3);
}

export function MetricChips({ data, max = 5 }: { data: Record<string, number>; max?: number }) {
  const entries = Object.entries(data || {})
    // surface badcase 修复率 first so it's never dropped by the cap
    .sort(([a], [b]) => (b === "badcase_fix_rate" ? 1 : 0) - (a === "badcase_fix_rate" ? 1 : 0));
  if (!entries.length) return <span className="text-slate-300">—</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.slice(0, max).map(([k, v]) => (
        <span key={k} className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[11.5px] text-slate-600">
          {k}=<span className="text-slate-900">{fmtMetric(k, v)}</span>
        </span>
      ))}
    </div>
  );
}
