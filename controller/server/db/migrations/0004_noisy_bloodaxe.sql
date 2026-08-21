CREATE TABLE "policy_record" (
	"id" text PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"description" text DEFAULT '' NOT NULL,
	"source" text DEFAULT 'custom' NOT NULL,
	"owner" text NOT NULL,
	"draft" jsonb NOT NULL,
	"draft_revision" integer DEFAULT 1 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "policy_validation_run" (
	"id" text PRIMARY KEY NOT NULL,
	"policy_id" text NOT NULL,
	"draft_revision" integer NOT NULL,
	"status" text DEFAULT 'queued' NOT NULL,
	"results" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"failure_reason" text,
	"created_by" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"completed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "policy_version" (
	"policy_id" text NOT NULL,
	"version" integer NOT NULL,
	"snapshot" jsonb NOT NULL,
	"checksum" text NOT NULL,
	"published_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "policy_version_policy_id_version_pk" PRIMARY KEY("policy_id","version")
);
--> statement-breakpoint
ALTER TABLE "policy_validation_run" ADD CONSTRAINT "policy_validation_run_policy_id_policy_record_id_fk" FOREIGN KEY ("policy_id") REFERENCES "public"."policy_record"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "policy_validation_run" ADD CONSTRAINT "policy_validation_run_created_by_auth_user_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."auth_user"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "policy_version" ADD CONSTRAINT "policy_version_policy_id_policy_record_id_fk" FOREIGN KEY ("policy_id") REFERENCES "public"."policy_record"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "policy_record_name_idx" ON "policy_record" USING btree ("name");--> statement-breakpoint
CREATE INDEX "policy_validation_run_policy_idx" ON "policy_validation_run" USING btree ("policy_id","created_at");--> statement-breakpoint
CREATE UNIQUE INDEX "policy_version_checksum_idx" ON "policy_version" USING btree ("checksum");