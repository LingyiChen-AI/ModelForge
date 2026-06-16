import type { ReactNode } from "react";
import { BarChart3, ClipboardCheck } from "lucide-react";
import { EvalPage } from "../pages/EvalPage";
import { PromptEvalsPage } from "../pages/PromptEvalsPage";
import { useAuth } from "../context/AuthContext";
import { navigate } from "../router";
import { cx } from "../ui";

type TabKey = "model" | "prompt";

// 「测试」模块外壳:模型测试(/eval)与 Prompt 评测(/eval/prompt)两个子 Tab。
// Tab 按权限显示;只有一个可见时不渲染切换条,直接落到对应子页。
export function TestModule({ active }: { active: TabKey }) {
  const { can } = useAuth();
  const tabs = [
    can("eval:read") && { key: "model" as const, label: "模型测试", icon: <BarChart3 size={15} />, href: "/eval" },
    can("prompteval:read") && { key: "prompt" as const, label: "Prompt 评测", icon: <ClipboardCheck size={15} />, href: "/eval/prompt" },
  ].filter(Boolean) as { key: TabKey; label: string; icon: ReactNode; href: string }[];

  const body = active === "prompt" ? <PromptEvalsPage /> : <EvalPage />;

  return (
    <>
      {tabs.length > 1 && (
        <div className="mb-4 inline-flex items-center gap-1 rounded-lg bg-slate-100 p-1">
          {tabs.map(t => {
            const on = t.key === active;
            return (
              <button
                key={t.key}
                onClick={() => navigate(t.href)}
                className={cx(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors cursor-pointer",
                  on ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700")}
              >
                {t.icon}{t.label}
              </button>
            );
          })}
        </div>
      )}
      {body}
    </>
  );
}
