import { eq } from "drizzle-orm";

import type { ControllerAuth } from "./auth.js";
import type { ControllerDatabase } from "./db/client.js";
import { account, user } from "./db/schema.js";

export async function ensureBootstrapAdmin(input: {
  auth: ControllerAuth;
  db: ControllerDatabase;
  email: string;
  password: string;
  name: string;
}): Promise<"created" | "existing"> {
  const [existing] = await input.db.select({ id: user.id }).from(user).where(eq(user.email, input.email)).limit(1);
  if (existing) {
    const linked = await input.db.select({ providerId: account.providerId }).from(account).where(eq(account.userId, existing.id));
    if (linked.some((item) => item.providerId === "credential")) return "existing";
    if (linked.length > 0) {
      throw new Error("Bootstrap administrator email is already linked to a non-credential Better Auth account.");
    }
    // Recover only an orphan left by an interrupted first bootstrap. Account
    // creation and password hashing below are still exclusively Better Auth's.
    await input.db.delete(user).where(eq(user.id, existing.id));
  }
  // Better Auth owns validation, password hashing, and account linking.
  await input.auth.api.createUser({
    body: { email: input.email, password: input.password, name: input.name, role: "admin" },
  });
  return "created";
}
