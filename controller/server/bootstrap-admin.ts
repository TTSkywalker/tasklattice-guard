import { loadConfig } from "./config.js";
import { createDatabase } from "./db/client.js";
import { createAuth } from "./auth.js";
import { runMigrations } from "./db/migrate.js";
import { ensureBootstrapAdmin } from "./bootstrap.js";

const email = process.env.CONTROLLER_BOOTSTRAP_ADMIN_EMAIL?.trim();
const password = process.env.CONTROLLER_BOOTSTRAP_ADMIN_PASSWORD;
const name = process.env.CONTROLLER_BOOTSTRAP_ADMIN_NAME?.trim() || "Administrator";

if (!email || !password) {
  throw new Error(
    "CONTROLLER_BOOTSTRAP_ADMIN_EMAIL and CONTROLLER_BOOTSTRAP_ADMIN_PASSWORD are required.",
  );
}

const config = loadConfig();
const { db, pool } = createDatabase(config);
const auth = createAuth(config, db);

try {
  await runMigrations(config, db);
  const status = await ensureBootstrapAdmin({ auth, db, email, password, name });
  process.stdout.write(`${status === "created" ? "Created" : "Found existing"} Better Auth administrator ${email}.\n`);
} finally {
  await pool.end();
}
