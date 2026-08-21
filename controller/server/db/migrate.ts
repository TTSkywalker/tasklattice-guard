import { migrate } from "drizzle-orm/node-postgres/migrator";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import type { ControllerConfig } from "../config.js";
import type { ControllerDatabase } from "./client.js";

export async function runMigrations(config: ControllerConfig, db: ControllerDatabase): Promise<void> {
  await migrate(db, { migrationsFolder: config.migrationsPath });
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const { loadConfig } = await import("../config.js");
  const { createDatabase } = await import("./client.js");
  const config = loadConfig();
  const { db, pool } = createDatabase(config);
  try {
    await runMigrations(config, db);
  } finally {
    await pool.end();
  }
}
