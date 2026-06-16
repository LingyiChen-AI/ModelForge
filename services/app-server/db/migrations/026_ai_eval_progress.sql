-- AI 自动评估的独立进度/状态(并发处理 + 进度可视),与跑输出的 status/progress 并行。
ALTER TABLE prompt_eval_runs ADD COLUMN IF NOT EXISTS ai_status TEXT;
ALTER TABLE prompt_eval_runs ADD COLUMN IF NOT EXISTS ai_progress DOUBLE PRECISION DEFAULT 0;
ALTER TABLE prompt_eval_runs ADD COLUMN IF NOT EXISTS ai_error TEXT;
