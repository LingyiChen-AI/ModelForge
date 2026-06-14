import { useEffect, useState } from "react";
import { CheckCircle2, XCircle, Info, X } from "lucide-react";
import { cx } from "./ui";

type ToastType = "error" | "success" | "info";
type Item = { id: number; msg: string; type: ToastType };

let _id = 0;
const listeners = new Set<(t: Item) => void>();

export function toast(msg: string, type: ToastType = "info") {
  listeners.forEach(l => l({ id: ++_id, msg, type }));
}
export const toastError = (m: string) => toast(m, "error");
export const toastSuccess = (m: string) => toast(m, "success");

const TONE: Record<ToastType, string> = {
  error: "text-red-700 ring-red-200",
  success: "text-emerald-700 ring-emerald-200",
  info: "text-slate-700 ring-slate-200",
};
const ICON = { error: XCircle, success: CheckCircle2, info: Info };

export function Toaster() {
  const [items, setItems] = useState<Item[]>([]);
  useEffect(() => {
    const on = (t: Item) => {
      setItems(s => [...s, t]);
      setTimeout(() => setItems(s => s.filter(x => x.id !== t.id)), 3500);
    };
    listeners.add(on);
    return () => { listeners.delete(on); };
  }, []);
  return (
    <div className="pointer-events-none fixed top-4 right-4 z-[100] flex flex-col gap-2">
      {items.map(t => {
        const Icon = ICON[t.type];
        return (
          <div key={t.id} className={cx("pointer-events-auto flex items-center gap-2.5 rounded-lg bg-white px-3.5 py-2.5 text-[13px] shadow-lg ring-1", TONE[t.type])}>
            <Icon size={16} className="shrink-0" />
            <span className="max-w-[320px] break-words">{t.msg}</span>
            <button onClick={() => setItems(s => s.filter(x => x.id !== t.id))} className="ml-1 shrink-0 text-slate-300 hover:text-slate-500 cursor-pointer"><X size={14} /></button>
          </div>
        );
      })}
    </div>
  );
}
