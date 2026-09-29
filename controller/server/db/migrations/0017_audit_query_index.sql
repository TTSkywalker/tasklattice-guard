CREATE INDEX IF NOT EXISTS "audit_time_id_idx" ON "audit_event" ("occurred_at" DESC, "id" DESC);
