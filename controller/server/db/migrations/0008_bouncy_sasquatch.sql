DROP INDEX "deployment_integration_route_order_idx";--> statement-breakpoint
ALTER TABLE "guardrail_deployment" ADD COLUMN "deleted_at" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "guardrail_deployment" ADD COLUMN "deleted_by" text;--> statement-breakpoint
ALTER TABLE "guardrail_deployment" ADD COLUMN "delete_reason" text;--> statement-breakpoint
ALTER TABLE "guardrail_deployment" ADD CONSTRAINT "guardrail_deployment_deleted_by_auth_user_id_fk" FOREIGN KEY ("deleted_by") REFERENCES "public"."auth_user"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "deployment_integration_route_order_idx" ON "guardrail_deployment" USING btree ("integration_id","route_order") WHERE "guardrail_deployment"."deleted_at" is null;