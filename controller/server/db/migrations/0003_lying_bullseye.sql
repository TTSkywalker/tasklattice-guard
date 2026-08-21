ALTER TABLE "guardrail_deployment" ALTER COLUMN "integration_id" DROP NOT NULL;--> statement-breakpoint
ALTER TABLE "guardrail_version" ALTER COLUMN "created_by" DROP NOT NULL;