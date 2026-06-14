-- Training can merge multiple train-set versions and multiple eval-set versions.
-- Keep the original single columns (primary / back-compat); add JSON lists holding
-- the full selection. Worker reads the lists, concatenates the snapshots.
ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS dataset_version_ids JSON;
ALTER TABLE training_jobs ADD COLUMN IF NOT EXISTS eval_dataset_version_ids JSON;
