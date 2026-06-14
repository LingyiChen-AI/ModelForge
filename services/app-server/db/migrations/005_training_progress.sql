-- Live training progress (0~1), updated by the worker during training.
ALTER TABLE training_jobs
    ADD COLUMN IF NOT EXISTS progress double precision NOT NULL DEFAULT 0;
