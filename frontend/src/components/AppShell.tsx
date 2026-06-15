import { useState, type ReactNode } from "react";
import {
  LayoutDashboard, Database, Cpu, Boxes, BarChart3, Rocket, Users, ShieldCheck,
  KeyRound, LogOut, PanelLeftClose, PanelLeftOpen, Bug,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { cx } from "../ui";
import { navigate } from "../router";
import { Logo } from "./Logo";

type NavItem = { href: string; label: string; icon: ReactNode; perm?: string; match: (p: string) => boolean };

const NAV: NavItem[] = [
  { href: "/", label: "概览", icon: <LayoutDashboard size={18} />, match: p => p === "/" },
  { href: "/datasets", label: "数据集", icon: <Database size={18} />, perm: "dataset:read", match: p => p.startsWith("/datasets") },
  { href: "/training", label: "训练", icon: <Cpu size={18} />, perm: "training:read", match: p => p.startsWith("/training") },
  { href: "/models", label: "模型", icon: <Boxes size={18} />, perm: "model:read", match: p => p.startsWith("/models") },
  { href: "/eval", label: "测试", icon: <BarChart3 size={18} />, perm: "eval:read", match: p => p.startsWith("/eval") },
  { href: "/deploy", label: "部署", icon: <Rocket size={18} />, perm: "deploy:read", match: p => p.startsWith("/deploy") },
  { href: "/badcase", label: "Badcase", icon: <Bug size={18} />, perm: "badcase:read", match: p => p.startsWith("/badcase") },
  { href: "/users", label: "用户", icon: <Users size={18} />, perm: "user:manage", match: p => p.startsWith("/users") },
  { href: "/roles", label: "角色", icon: <ShieldCheck size={18} />, perm: "role:manage", match: p => p.startsWith("/roles") },
  { href: "/api-keys", label: "API Key", icon: <KeyRound size={18} />, perm: "apikey:manage", match: p => p.startsWith("/api-keys") },
];

function initials(name: string) {
  return (name || "?").trim().slice(0, 2).toUpperCase();
}

export function AppShell({ path, children }: { path: string; children: ReactNode }) {
  const { me, can, logout } = useAuth();
  // collapsed = icon rail; expanded = labels. Start collapsed on small screens.
  const [collapsed, setCollapsed] = useState(() => typeof window !== "undefined" && window.innerWidth < 1024);
  const items = NAV.filter(n => !n.perm || can(n.perm));

  return (
    <div className="min-h-dvh bg-slate-50">
      {/* sidebar — part of the layout (pushes content), collapses to an icon rail */}
      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-30 flex flex-col bg-ink-900 text-slate-300 transition-[width] duration-200",
          collapsed ? "w-16" : "w-60")}
      >
        <div className={cx("flex h-16 items-center border-b border-white/5", collapsed ? "justify-center" : "gap-2.5 px-5")}>
          <Logo size={collapsed ? 30 : 34} />
          {!collapsed && (
            <div className="leading-tight">
              <div className="text-[15px] font-semibold text-white tracking-tight">ModelForge</div>
              <div className="text-[10.5px] uppercase tracking-widest text-slate-500">ML Platform</div>
            </div>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-0.5">
          {items.map(n => {
            const active = n.match(path);
            return (
              <a
                key={n.href}
                href={n.href}
                title={collapsed ? n.label : undefined}
                onClick={(e) => { e.preventDefault(); navigate(n.href); }}
                className={cx(
                  "group relative flex items-center rounded-lg py-2 text-[13.5px] font-medium transition-colors",
                  collapsed ? "justify-center px-0" : "gap-3 px-3",
                  active ? "bg-brand-500/12 text-white" : "text-slate-400 hover:text-white hover:bg-white/5")}
              >
                {active && <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-brand-400" />}
                <span className={cx(active ? "text-brand-400" : "text-slate-500 group-hover:text-slate-300")}>{n.icon}</span>
                {!collapsed && n.label}
              </a>
            );
          })}
        </nav>

        <div className="border-t border-white/5 p-3">
          {collapsed ? (
            <div className="flex flex-col items-center gap-2">
              <div title={`${me?.name ?? ""} · ${me?.role ?? ""}`}
                   className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500/20 text-[12px] font-semibold text-brand-300 ring-1 ring-brand-500/30">
                {initials(me?.name ?? "")}
              </div>
              <button onClick={logout} title="登出"
                className="flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-white/5 hover:text-red-400 cursor-pointer">
                <LogOut size={15} />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded-lg px-2 py-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500/20 text-[12px] font-semibold text-brand-300 ring-1 ring-brand-500/30">
                {initials(me?.name ?? "")}
              </div>
              <div className="min-w-0 flex-1 leading-tight">
                <div className="truncate text-[13px] font-medium text-white">{me?.name}</div>
                <div className="truncate text-[11px] text-slate-500">{me?.role}</div>
              </div>
              <button onClick={logout} title="登出"
                className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-white/5 hover:text-red-400 cursor-pointer">
                <LogOut size={16} />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* content — padding tracks the sidebar width so nothing is ever covered */}
      <div className={cx("transition-[padding] duration-200", collapsed ? "pl-16" : "pl-60")}>
        <div className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur">
          <button
            onClick={() => setCollapsed(c => !c)}
            title={collapsed ? "展开菜单" : "收起菜单"}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 cursor-pointer"
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>

        <main className="px-4 py-4 sm:px-6">{children}</main>
      </div>
    </div>
  );
}
