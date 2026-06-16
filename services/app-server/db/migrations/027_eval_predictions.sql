-- 模型测试逐条预测落库,供「导出预测结果表格」使用。
-- 元素形如 {"row": int, "input": str, "expected": str, "predicted": str, "correct": bool}。
ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS predictions JSON DEFAULT '[]'::json;
