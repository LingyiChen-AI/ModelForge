export type Seg = { label: string; value: number; color: string };

// Donut chart with center total + legend (pure SVG, no deps).
export function Donut({ data }: { data: Seg[] }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const r = 42, c = 2 * Math.PI * r, sw = 14;
  let off = 0;
  return (
    <div className="flex items-center gap-6">
      <div className="relative h-[120px] w-[120px] shrink-0">
        <svg viewBox="0 0 100 100" className="-rotate-90">
          <circle cx="50" cy="50" r={r} fill="none" stroke="#f1f5f9" strokeWidth={sw} />
          {total > 0 && data.map((s, i) => {
            const len = (s.value / total) * c;
            const node = (
              <circle key={i} cx="50" cy="50" r={r} fill="none" stroke={s.color} strokeWidth={sw}
                strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-off} />
            );
            off += len;
            return node;
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="tnum text-[22px] font-semibold text-slate-900">{total}</div>
          <div className="text-[11px] text-slate-400">总计</div>
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {data.length === 0 && <span className="text-[12.5px] text-slate-400">暂无数据</span>}
        {data.map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-[12.5px]">
            <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: s.color }} />
            <span className="text-slate-600">{s.label}</span>
            <span className="tnum ml-auto pl-4 font-medium text-slate-800">{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Horizontal bar list for category counts.
export function BarList({ data }: { data: Seg[] }) {
  if (data.length === 0) return <div className="py-8 text-center text-[12.5px] text-slate-400">暂无数据</div>;
  const max = Math.max(1, ...data.map(d => d.value));
  return (
    <div className="flex flex-col gap-3.5">
      {data.map((d, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="w-24 shrink-0 truncate text-[12.5px] text-slate-500">{d.label}</div>
          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full transition-all" style={{ width: `${(d.value / max) * 100}%`, background: d.color }} />
          </div>
          <div className="w-8 shrink-0 text-right tnum text-[12.5px] font-medium text-slate-700">{d.value}</div>
        </div>
      ))}
    </div>
  );
}
