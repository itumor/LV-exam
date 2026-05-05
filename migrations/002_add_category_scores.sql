-- Add exam_attempt_category_score table for storing per-category scores
CREATE TABLE IF NOT EXISTS exam_attempt_category_score (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('listening', 'reading', 'writing', 'speaking')),
    score_0_to_15 INTEGER NOT NULL CHECK (score_0_to_15 >= 0 AND score_0_to_15 <= 15),
    passed_boolean BOOLEAN NOT NULL,
    created_at TEXT NOT NULL
);

-- Add index for faster lookup by attempt and category
CREATE INDEX IF NOT EXISTS idx_exam_attempt_category_score_attempt_category 
ON exam_attempt_category_score(attempt_id, category);

-- Add index for faster lookup by account and category for analytics
CREATE INDEX IF NOT EXISTS idx_exam_attempt_category_score_account_category 
ON exam_attempt_category_score(account_id, category, created_at DESC);