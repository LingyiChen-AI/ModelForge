-- Training binds an eval set (validation during training), in addition to the train set.
ALTER TABLE training_jobs
    ADD COLUMN IF NOT EXISTS eval_dataset_version_id integer REFERENCES dataset_versions(id);
