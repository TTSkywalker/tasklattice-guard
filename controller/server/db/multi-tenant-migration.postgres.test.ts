// @vitest-environment node
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { Pool } from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const url = process.env.GUARD_TEST_POSTGRES_URL;

describe.skipIf(!url)("multi-tenant migration of populated Controller tables", () => {
  const namespace = `guard_tenant_migration_${randomUUID().replaceAll("-", "")}`;
  let admin: Pool;
  let pool: Pool;
  const read = (name: string) => readFileSync(new URL(`./migrations/${name}`, import.meta.url), "utf8");

  beforeAll(async () => {
    expect(["127.0.0.1", "localhost", "[::1]"]).toContain(new URL(url!).hostname);
    admin = new Pool({ connectionString: url, max: 1 });
    await admin.query(`CREATE SCHEMA "${namespace}"`);
    pool = new Pool({ connectionString: url, max: 2, options: `-c search_path=${namespace}`, application_name: namespace });
    const journal = JSON.parse(read("meta/_journal.json")) as { entries: { tag: string }[] };
    for (const { tag } of journal.entries.filter(entry => entry.tag !== "0013_multi_tenant_resources")) {
      await pool.query(read(`${tag}.sql`).replaceAll('"public".', `"${namespace}".`));
    }
    await pool.query(`
      INSERT INTO auth_user (id,name,email,role) VALUES ('legacy-admin','Admin','legacy@example.test','admin');
      INSERT INTO policy_record (id,name,owner,draft) VALUES ('legacy-policy','Policy','legacy-admin','{}');
      INSERT INTO guardrail (id,name,draft_config) VALUES ('legacy-guardrail','Guardrail','{}');
      INSERT INTO runner_pool (id,name) VALUES ('default','Default');
      INSERT INTO endpoint (id,name,adapter) VALUES ('legacy-endpoint','Endpoint','HTTP');
      INSERT INTO guardrail_router (id,name,guardrail_id,endpoint_id,pool_id) VALUES ('legacy-router','Router','legacy-guardrail','legacy-endpoint','default');
      INSERT INTO traffic_router (id,name,draft) VALUES ('legacy-traffic-router','Traffic Router','{"routes":[]}');
      INSERT INTO model_provider (id,name,kind,base_url,credential_ciphertext) VALUES ('legacy-provider','Provider','custom-openai-compatible','http://provider.invalid/v1','');
      INSERT INTO model_definition (id,provider_id,name,model) VALUES ('legacy-model','legacy-provider','Model','legacy');
      INSERT INTO model_configuration_revision (id,revision,assignments) VALUES ('legacy-model-revision',1,'{"controlPlane":null,"bindings":{}}');
      INSERT INTO runtime_event (id,occurred_at,request_id,runner_id,direction,decision,duration_ms) VALUES ('legacy-event',now(),'legacy-request','runner','incoming','allow',1);
      INSERT INTO audit_event (id,kind,actor_id,resource_type,resource_id) VALUES ('legacy-audit','legacy.created','legacy-admin','guardrail','legacy-guardrail');
    `);
    await pool.query(read("0013_multi_tenant_resources.sql"));
  });

  afterAll(async () => {
    await pool?.end();
    await admin?.query(`DROP SCHEMA IF EXISTS "${namespace}" CASCADE`);
    await admin?.end();
  });

  it("backfills existing resources and allows the same Provider name in another tenant", async () => {
    for (const table of ["auth_user", "policy_record", "guardrail", "endpoint", "guardrail_router",
      "traffic_router", "model_provider", "model_definition", "model_configuration_revision", "runtime_event", "audit_event"]) {
      const result = await pool.query(`SELECT DISTINCT tenant_id FROM "${table}"`);
      expect(result.rows, table).toEqual([{ tenant_id: "tenantA" }]);
    }
    expect((await pool.query("SELECT id FROM tenant ORDER BY id")).rows).toEqual([
      { id: "tenantA" }, { id: "tenantB" }, { id: "tenantC" },
    ]);
    await pool.query("INSERT INTO model_provider (id,tenant_id,name,kind,base_url,credential_ciphertext) VALUES ('provider-b','tenantB','Provider','custom-openai-compatible','http://provider.invalid/v1','')");
    expect((await pool.query("SELECT tenant_id FROM model_provider WHERE name = 'Provider' ORDER BY tenant_id")).rows)
      .toEqual([{ tenant_id: "tenantA" }, { tenant_id: "tenantB" }]);
  });
});
