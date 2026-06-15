ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS winner_arm_id INTEGER REFERENCES prompt_eval_arms(id);
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS all_bad BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS is_good BOOLEAN;
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS evaluated_by INTEGER REFERENCES users(id);
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMP;
