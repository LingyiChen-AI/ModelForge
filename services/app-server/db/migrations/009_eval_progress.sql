-- Live eval/test progress (0~1), updated by the worker during model testing.
ALTER TABLE eval_runs
    ADD COLUMN IF NOT EXISTS progress double precision NOT NULL DEFAULT 0;
