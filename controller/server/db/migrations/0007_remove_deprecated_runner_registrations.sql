-- Runner registrations are current capacity state, not runtime or audit history.
-- Remove only offline identities created by the former Deployment/StatefulSet
-- name that exposed the internal `default` pool ID.
DELETE FROM "runner_instance"
WHERE "pool_id" = 'default'
	AND "status" = 'offline'
	AND "runner_id" LIKE '%-runner-default-%';
