import { createDecipheriv } from "node:crypto";

const PREFIX = "tasklattice-runtime-log-v1";

export function decodeRuntimeLogKey(value: string | null | undefined): Buffer | null {
  if (!value) return null;
  const trimmed = value.trim();
  const decoded = Buffer.from(trimmed, "base64");
  if (decoded.length !== 32 || decoded.toString("base64").replace(/=+$/, "") !== trimmed.replace(/=+$/, "")) {
    throw new Error("MODEL_GUARDRAILS_RUNTIME_LOG_ENCRYPTION_KEY must be a base64-encoded 32-byte key.");
  }
  return decoded;
}

export function decryptRuntimeLogPayload(value: unknown, key: Buffer | null): Record<string, unknown> | null {
  if (!key || typeof value !== "string") return null;
  const [prefix, nonceValue, tagValue, ciphertextValue] = value.split(":");
  if (prefix !== PREFIX || !nonceValue || !tagValue || !ciphertextValue) return null;
  try {
    const decipher = createDecipheriv("aes-256-gcm", key, Buffer.from(nonceValue, "base64"));
    decipher.setAAD(Buffer.from(PREFIX));
    decipher.setAuthTag(Buffer.from(tagValue, "base64"));
    const plaintext = Buffer.concat([decipher.update(Buffer.from(ciphertextValue, "base64")), decipher.final()]);
    const decoded = JSON.parse(plaintext.toString("utf8"));
    return decoded && typeof decoded === "object" && !Array.isArray(decoded) ? decoded as Record<string, unknown> : null;
  } catch {
    return null;
  }
}
