import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { Loader2 } from "lucide-react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type Variant = "primary" | "ghost" | "subtle" | "danger";
export function Button({
  variant = "ghost", size = "md", className, children, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "md" | "sm" }) {
  return (
    <button
      className={cx("btn", `btn-${variant}`, size === "sm" && "btn-sm", className)}
      {...rest}
    >
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
    <label className="flex flex-col gap-1.5">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="text-xs text-slate-400">{hint}</span>}
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
export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status?.toLowerCase()] ?? "gray";
  return <Badge tone={tone} dot>{status}</Badge>;
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx("animate-spin", className)} />;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
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

export function TableShell({ head, children, empty }: { head: ReactNode; children: ReactNode; empty?: boolean }) {
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="tbl">
          <thead><tr>{head}</tr></thead>
          {!empty && <tbody>{children}</tbody>}
        </table>
      </div>
      {empty && children}
    </Card>
  );
}
