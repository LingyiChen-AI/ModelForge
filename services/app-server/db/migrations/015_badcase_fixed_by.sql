-- Track which model versions have repaired each badcase (V4 已修复 / V7 已修复).
ALTER TABLE badcases ADD COLUMN IF NOT EXISTS fixed_by JSON DEFAULT '[]'::json;
