import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Loader2, X, ChevronRight, Check } from "lucide-react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

// Server stores local-time (DB tz = Asia/Shanghai) naive timestamps — render the
// date/time components verbatim, no timezone math (avoids a spurious +8h shift).
export function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : "—";
}

// Compact creator + created-time cell pair used across list tables.
export function Creator({ name }: { name?: string | null }) {
  return <span className="text-[13px] text-slate-500">{name || "—"}</span>;
}
export function CreatedAt({ at }: { at?: string | null }) {
  return <span className="tnum whitespace-nowrap text-[12.5px] text-slate-400">{fmtTime(at)}</span>;
}

type Variant = "primary" | "ghost" | "subtle" | "danger";
export function Button({
  variant = "ghost", size = "md", className, children, loading, disabled, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "md" | "sm"; loading?: boolean }) {
  return (
    <button
      className={cx("btn", `btn-${variant}`, size === "sm" && "btn-sm", className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Loader2 className="animate-spin" size={size === "sm" ? 13 : 16} />}
      {children}
    </button>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx("card", className)}>{children}</div>;
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx("input", className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cx("input", className)} {...rest}>{children}</select>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="relative flex flex-col gap-1.5">
      <span className="label">{label}</span>
      {children}
      {/* hint floats below the input (out of flow) so fields keep equal height and align in a row */}
      {hint && <span className="pointer-events-none absolute top-full left-0 mt-1 whitespace-nowrap text-xs text-slate-400">{hint}</span>}
    </label>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("font-mono text-[12.5px] text-slate-500", className)}>{children}</span>;
}

const TONES: Record<string, string> = {
  green: "bg-brand-50 text-brand-700 ring-brand-200",
  blue: "bg-blue-50 text-blue-700 ring-blue-200",
  amber: "bg-amber-50 text-amber-700 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  gray: "bg-slate-100 text-slate-600 ring-slate-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  cyan: "bg-cyan-50 text-cyan-700 ring-cyan-200",
};
const DOT: Record<string, string> = {
  green: "bg-brand-500", blue: "bg-blue-500", amber: "bg-amber-500",
  red: "bg-red-500", gray: "bg-slate-400", violet: "bg-violet-500", cyan: "bg-cyan-500",
};

export function Badge({ tone = "gray", dot, children }: { tone?: keyof typeof TONES; dot?: boolean; children: ReactNode }) {
  return (
    <span className={cx("badge", TONES[tone])}>
      {dot && <span className={cx("h-1.5 w-1.5 rounded-full", DOT[tone])} />}
      {children}
    </span>
  );
}

const STATUS_TONE: Record<string, keyof typeof TONES> = {
  succeeded: "green", running: "blue", pending: "amber", failed: "red",
  cancelled: "gray", stopped: "gray", none: "gray", staging: "amber", prod: "green",
};
// Hover tooltip rendered into a portal so it's never clipped by table overflow.
export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const show = () => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setPos({ x: r.left, y: r.bottom + 6 });
  };
  return (
    <span ref={ref} onMouseEnter={show} onMouseLeave={() => setPos(null)}
          className="inline-flex cursor-help align-middle">
      {children}
      {pos && createPortal(
        <span style={{ position: "fixed", left: pos.x, top: pos.y, zIndex: 1000 }}
              className="pointer-events-none w-72 max-w-[18rem] whitespace-normal break-words rounded-lg bg-slate-900 px-3 py-2 text-[12px] leading-relaxed text-slate-100 shadow-lg">
          {content}
        </span>, document.body)}
    </span>
  );
}

export function StatusBadge({ status, error }: { status: string; error?: string | null }) {
  const tone = STATUS_TONE[status?.toLowerCase()] ?? "gray";
  const badge = <Badge tone={tone} dot>{status}</Badge>;
  if (!error) return badge;
  // keep the row clean — same look as other badges, surface the hint/error only on hover
  return <Tooltip content={error}><span className="cursor-help">{badge}</span></Tooltip>;
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx("animate-spin", className)} />;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
      <div>
        <h1 className="text-[22px] leading-7 text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-[13px] text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ icon, title, hint }: { icon: ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-400">{icon}</div>
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {hint && <p className="text-xs text-slate-400 max-w-xs">{hint}</p>}
    </div>
  );
}

export function TableShell({ head, children, empty, loading }: { head: ReactNode; children: ReactNode; empty?: boolean; loading?: boolean }) {
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="tbl">
          <thead><tr>{head}</tr></thead>
          {!empty && !loading && <tbody>{children}</tbody>}
        </table>
      </div>
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-slate-400">
          <Spinner className="h-5 w-5" /> <span className="text-[13px]">加载中…</span>
        </div>
      ) : empty ? children : null}
    </Card>
  );
}

// Two-column cascade picker (left = group, right = its leaves).
// Single-select by default; pass `multiple` for checkbox multi-select (value = string[]).
export type CascadeGroup = {
  key: string; label: string; count?: number;
  items: { value: string; label: string; hint?: string }[];
};
export function Cascade({
  groups, value, onChange, multiple = false, emptyHint = "暂无可选项", rightEmptyHint = "该项下暂无内容",
}: {
  groups: CascadeGroup[]; value: string | string[]; onChange: (v: any) => void;
  multiple?: boolean; emptyHint?: string; rightEmptyHint?: string;
}) {
  const selected: string[] = multiple ? (Array.isArray(value) ? value : []) : (value ? [value as string] : []);
  const isSel = (v: string) => selected.includes(v);
  const pick = (v: string) => {
    if (!multiple) { onChange(v); return; }
    onChange(isSel(v) ? selected.filter(x => x !== v) : [...selected, v]);
  };
  const groupOfValue = groups.find(g => g.items.some(i => selected.includes(i.value)))?.key;
  const [active, setActive] = useState(groupOfValue ?? groups[0]?.key ?? "");
  useEffect(() => {
    if (!groups.find(g => g.key === active)) setActive(groupOfValue ?? groups[0]?.key ?? "");
  }, [groups, active, groupOfValue]);

  if (groups.length === 0) {
    return <div className="rounded-lg border border-slate-200 px-3 py-6 text-center text-[13px] text-slate-400">{emptyHint}</div>;
  }
  const activeGroup = groups.find(g => g.key === active) ?? groups[0];
  return (
    <div className="grid grid-cols-2 overflow-hidden rounded-lg border border-slate-200">
      <div className="max-h-64 overflow-y-auto border-r border-slate-200 bg-slate-50/50">
        {groups.map(g => {
          const on = g.key === activeGroup.key;
          const picked = g.items.some(i => isSel(i.value));
          return (
            <button
              key={g.key} type="button" onClick={() => setActive(g.key)}
              className={cx("flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2 text-left text-[13px] transition",
                on ? "bg-white font-medium text-slate-800" : "text-slate-600 hover:bg-white/70")}
            >
              <span className="flex items-center gap-1.5 truncate">
                {picked && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />}
                <span className="truncate">{g.label}</span>
                {g.count != null && <span className="text-slate-400">({g.count})</span>}
              </span>
              <ChevronRight size={14} className={cx("shrink-0", on ? "text-slate-400" : "text-slate-300")} />
            </button>
          );
        })}
      </div>
      <div className="max-h-64 overflow-y-auto">
        {activeGroup.items.length === 0 ? (
          <div className="px-3 py-6 text-center text-[12.5px] text-slate-400">{rightEmptyHint}</div>
        ) : activeGroup.items.map(it => {
          const sel = isSel(it.value);
          return (
            <button
              key={it.value} type="button" onClick={() => pick(it.value)}
              className={cx("flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2 text-left text-[13px] transition",
                sel ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-50")}
            >
              <span className="flex items-center gap-2 truncate">
                <span className={cx("flex h-4 w-4 shrink-0 items-center justify-center border",
                  multiple ? "rounded" : "rounded-full",
                  sel ? "border-brand-500 bg-brand-500 text-white" : "border-slate-300")}>
                  {sel && <Check size={11} strokeWidth={3} />}
                </span>
                <span className="truncate">{it.label}</span>
              </span>
              {it.hint && <span className="shrink-0 text-[11.5px] text-slate-400">{it.hint}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// Centered confirm dialog with an optional "also delete managed data" checkbox.
export function ConfirmDialog({
  open, title, message, cascadeLabel, confirmText = "删除", busy, onCancel, onConfirm,
}: {
  open: boolean; title: string; message?: ReactNode; cascadeLabel?: ReactNode;
  confirmText?: string; busy?: boolean; onCancel: () => void; onConfirm: (cascade: boolean) => void;
}) {
  const [cascade, setCascade] = useState(false);
  useEffect(() => { if (open) setCascade(false); }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, onCancel]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={onCancel} />
      <div role="dialog" aria-modal="true" className="relative w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
        <h2 className="text-[16px] font-semibold text-slate-900">{title}</h2>
        {message && <div className="mt-2 text-[13px] leading-relaxed text-slate-500">{message}</div>}
        {cascadeLabel && (
          <label className="mt-4 flex cursor-pointer items-start gap-2.5 rounded-lg border border-slate-200 p-3 hover:border-slate-300">
            <input type="checkbox" checked={cascade} onChange={e => setCascade(e.target.checked)} className="mt-0.5 accent-red-500" />
            <span className="text-[12.5px] text-slate-600">{cascadeLabel}</span>
          </label>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="subtle" disabled={busy} onClick={onCancel}>取消</Button>
          <Button variant="danger" loading={busy} onClick={() => onConfirm(cascade)}>{confirmText}</Button>
        </div>
      </div>
    </div>
  );
}

// Small centered dialog with a single text input (replaces window.prompt).
export function PromptDialog({
  open, title, label, placeholder, confirmText = "确定", busy, onCancel, onConfirm,
}: {
  open: boolean; title: string; label?: string; placeholder?: string;
  confirmText?: string; busy?: boolean; onCancel: () => void; onConfirm: (value: string) => void;
}) {
  const [val, setVal] = useState("");
  useEffect(() => { if (open) setVal(""); }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, onCancel]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={onCancel} />
      <div role="dialog" aria-modal="true" className="relative w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl">
        <h2 className="text-[16px] font-semibold text-slate-900">{title}</h2>
        {label && <div className="mt-1 text-[12.5px] text-slate-500">{label}</div>}
        <Input
          className="mt-3" autoFocus placeholder={placeholder} value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && val) onConfirm(val); }}
        />
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="subtle" disabled={busy} onClick={onCancel}>取消</Button>
          <Button variant="primary" disabled={!val} loading={busy} onClick={() => onConfirm(val)}>{confirmText}</Button>
        </div>
      </div>
    </div>
  );
}

// Right-side slide-in drawer. Stays mounted so open/close animate; closes on
// backdrop click, Esc, or the close button. Locks body scroll while open.
export function Drawer({
  open, onClose, title, subtitle, footer, children, width = "max-w-lg",
}: {
  open: boolean; onClose: () => void; title: string; subtitle?: string;
  footer?: ReactNode; children: ReactNode; width?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, onClose]);

  return (
    <div className={cx("fixed inset-0 z-50", !open && "pointer-events-none")} aria-hidden={!open}>
      <div
        onClick={onClose}
        className={cx("absolute inset-0 bg-slate-900/30 backdrop-blur-sm transition-opacity duration-300",
          open ? "opacity-100" : "opacity-0")}
      />
      <div
        role="dialog" aria-modal="true" aria-label={title}
        className={cx(
          "absolute right-0 top-0 flex h-full w-full flex-col bg-white shadow-2xl transition-transform duration-300 ease-out",
          width, open ? "translate-x-0" : "translate-x-full")}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-[16px] font-semibold text-slate-900">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[12.5px] text-slate-500">{subtitle}</p>}
          </div>
          <button
            onClick={onClose} aria-label="关闭"
            className="-mr-1 rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="border-t border-slate-100 bg-slate-50/60 px-5 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}
