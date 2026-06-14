import { useState, type ReactNode } from "react";
import {
  Database, Cpu, Boxes, BarChart3, Rocket, Users, ShieldCheck,
  LogOut, Menu, X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { cx } from "../ui";
import { navigate } from "../router";
import { Logo } from "./Logo";

type NavItem = { href: string; label: string; icon: ReactNode; perm?: string; match: (p: string) => boolean };

const NAV: NavItem[] = [
  { href: "/", label: "数据集", icon: <Database size={18} />, perm: "dataset:read", match: p => p === "/" || p.startsWith("/datasets") },
  { href: "/training", label: "训练", icon: <Cpu size={18} />, perm: "training:read", match: p => p.startsWith("/training") },
  { href: "/models", label: "模型", icon: <Boxes size={18} />, perm: "model:read", match: p => p.startsWith("/models") },
  { href: "/eval", label: "评估", icon: <BarChart3 size={18} />, perm: "eval:read", match: p => p.startsWith("/eval") },
  { href: "/deploy", label: "部署", icon: <Rocket size={18} />, perm: "deploy:read", match: p => p.startsWith("/deploy") },
  { href: "/users", label: "用户", icon: <Users size={18} />, perm: "user:manage", match: p => p.startsWith("/users") },
  { href: "/roles", label: "角色", icon: <ShieldCheck size={18} />, perm: "role:manage", match: p => p.startsWith("/roles") },
];

function initials(name: string) {
  return (name || "?").trim().slice(0, 2).toUpperCase();
}

export function AppShell({ path, children }: { path: string; children: ReactNode }) {
  const { me, can, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const items = NAV.filter(n => !n.perm || can(n.perm));

  const sidebar = (
    <div className="flex h-full flex-col bg-ink-900 text-slate-300">
      <div className="flex items-center gap-2.5 px-5 h-16 border-b border-white/5">
        <Logo size={34} />
        <div className="leading-tight">
          <div className="text-[15px] font-semibold text-white tracking-tight">ModelForge</div>
          <div className="text-[10.5px] uppercase tracking-widest text-slate-500">ML Platform</div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-0.5">
        {items.map(n => {
          const active = n.match(path);
          return (
            <a
              key={n.href}
              href={n.href}
              onClick={(e) => { e.preventDefault(); setOpen(false); navigate(n.href); }}
              className={cx(
                "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors",
                active
                  ? "bg-brand-500/12 text-white"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              )}
            >
              {active && <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-brand-400" />}
              <span className={cx(active ? "text-brand-400" : "text-slate-500 group-hover:text-slate-300")}>{n.icon}</span>
              {n.label}
            </a>
          );
        })}
      </nav>

      <div className="border-t border-white/5 p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500/20 text-[12px] font-semibold text-brand-300 ring-1 ring-brand-500/30">
            {initials(me?.name ?? "")}
          </div>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="truncate text-[13px] font-medium text-white">{me?.name}</div>
            <div className="truncate text-[11px] text-slate-500">{me?.role}</div>
          </div>
          <button
            onClick={logout}
            title="登出"
            className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-white/5 hover:text-red-400 cursor-pointer"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh bg-slate-50">
      {/* desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 lg:block">{sidebar}</aside>

      {/* mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink-950/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 shadow-2xl">{sidebar}</aside>
        </div>
      )}

      <div className="lg:pl-60">
        {/* mobile top bar */}
        <div className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur lg:hidden">
          <button onClick={() => setOpen(true)} className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 cursor-pointer">
            {open ? <X size={18} /> : <Menu size={18} />}
          </button>
          <span className="text-sm font-semibold text-slate-900">ModelForge</span>
        </div>

        <main className="mx-auto max-w-7xl px-5 py-7 sm:px-8">{children}</main>
      </div>
    </div>
  );
}
