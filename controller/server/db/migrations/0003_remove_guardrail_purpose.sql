-- Guardrails are defined by their Policy bindings, not a separate business identity.
-- This intentionally removes the obsolete values; published artifacts stay immutable.
ALTER TABLE "guardrail" DROP COLUMN "description";
--> statement-breakpoint
-- Removing runtime context changes a draft. Old validation results must not
-- certify this new composition; active signed versions remain unchanged.
UPDATE "guardrail"
SET "draft_config" = "draft_config" - 'purposeDetails',
    "draft_revision" = "draft_revision" + 1,
    "updated_at" = NOW();
