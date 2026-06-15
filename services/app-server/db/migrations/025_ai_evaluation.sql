ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_winner_arm_id INTEGER REFERENCES prompt_eval_arms(id);
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_all_bad BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_is_good BOOLEAN;
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_model_id INTEGER REFERENCES llm_models(id);
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_reasoning TEXT;
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_evaluated_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
