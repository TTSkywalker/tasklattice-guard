UPDATE "runner_pool"
SET
	"name" = 'GuardRails 0',
	"desired_replicas" = CASE WHEN "desired_replicas" = 1 THEN 2 ELSE "desired_replicas" END,
	"updated_at" = now()
WHERE "id" = 'default';
