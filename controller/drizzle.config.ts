import { defineConfig } from "drizzle-kit";

if (!process.env.CONTROLLER_DATABASE_URL) {
  throw new Error("CONTROLLER_DATABASE_URL is required to generate migrations.");
}

export default defineConfig({
  dialect: "postgresql",
  schema: "./server/db/schema.ts",
  out: "./server/db/migrations",
  dbCredentials: { url: process.env.CONTROLLER_DATABASE_URL },
  strict: true,
});
