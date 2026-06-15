// Renders a hyperparameter dict as raw key=value chips (no metric-style rounding —
// e.g. lr=0.00005 must stay precise). Objects (e.g. negatives) are JSON-stringified.
export function ParamChips({ data }: { data: Record<string, any> }) {
  const entries = Object.entries(data || {});
  if (!entries.length) return <span className="text-slate-300">—</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([k, v]) => (
        <span key={k} className="rounded-md bg-slate-50 px-1.5 py-0.5 font-mono text-[11.5px] text-slate-500 ring-1 ring-slate-100">
          {k}=<span className="text-slate-700">{typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)}</span>
        </span>
      ))}
    </div>
  );
}
