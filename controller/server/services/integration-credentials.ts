import { createHash, randomBytes, randomUUID } from "node:crypto";

export const LEGACY_INTEGRATION_CREDENTIAL_ID = "legacy";

export type StoredIntegrationCredential = {
  id: string;
  sha256: string;
  keyHint: string;
  createdAt: string;
  revokedAt: string | null;
};

export type PublicIntegrationCredential = Pick<StoredIntegrationCredential, "id" | "keyHint" | "createdAt">;

export type IssuedIntegrationCredential = {
  value: string;
  stored: StoredIntegrationCredential;
  publicCredential: PublicIntegrationCredential;
};

export function issueIntegrationCredential(now = new Date()): IssuedIntegrationCredential {
  const value = `tg_${randomBytes(32).toString("base64url")}`;
  const stored = {
    id: randomUUID(),
    sha256: createHash("sha256").update(value).digest("hex"),
    keyHint: credentialHint(value),
    createdAt: now.toISOString(),
    revokedAt: null,
  } satisfies StoredIntegrationCredential;
  return {
    value,
    stored,
    publicCredential: toPublicCredential(stored),
  };
}

export function activeIntegrationCredentials(
  verification: Record<string, unknown>,
  legacyCreatedAt: Date,
): StoredIntegrationCredential[] {
  return allIntegrationCredentials(verification, legacyCreatedAt)
    .filter((credential) => credential.revokedAt === null)
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

export function publicIntegrationCredentials(
  verification: Record<string, unknown>,
  legacyCreatedAt: Date,
): PublicIntegrationCredential[] {
  return activeIntegrationCredentials(verification, legacyCreatedAt).map(toPublicCredential);
}

export function appendIntegrationCredential(
  verification: Record<string, unknown>,
  credential: StoredIntegrationCredential,
): Record<string, unknown> {
  const structured = structuredCredentials(verification);
  return {
    ...verification,
    credentials: [...structured, credential],
  };
}

export function revokeIntegrationCredentialDigest(
  verification: Record<string, unknown>,
  credentialId: string,
  now: Date,
): Record<string, unknown> | null {
  if (credentialId === LEGACY_INTEGRATION_CREDENTIAL_ID) {
    if (typeof verification.credentialSha256 !== "string") return null;
    const { credentialSha256: _removed, ...remaining } = verification;
    return remaining;
  }

  let found = false;
  const credentials = structuredCredentials(verification).map((credential) => {
    if (credential.id !== credentialId || credential.revokedAt !== null) return credential;
    found = true;
    return { ...credential, revokedAt: now.toISOString() };
  });
  return found ? { ...verification, credentials } : null;
}

function allIntegrationCredentials(
  verification: Record<string, unknown>,
  legacyCreatedAt: Date,
): StoredIntegrationCredential[] {
  const credentials = structuredCredentials(verification);
  if (typeof verification.credentialSha256 === "string" && verification.credentialSha256) {
    credentials.push({
      id: LEGACY_INTEGRATION_CREDENTIAL_ID,
      sha256: verification.credentialSha256,
      keyHint: "legacy credential",
      createdAt: legacyCreatedAt.toISOString(),
      revokedAt: null,
    });
  }
  return credentials;
}

function structuredCredentials(verification: Record<string, unknown>): StoredIntegrationCredential[] {
  if (!Array.isArray(verification.credentials)) return [];
  return verification.credentials.flatMap((value) => {
    if (!isRecord(value)) return [];
    const id = nonEmptyString(value.id);
    const sha256 = nonEmptyString(value.sha256);
    const keyHint = nonEmptyString(value.keyHint);
    const createdAt = nonEmptyString(value.createdAt);
    if (!id || !sha256 || !keyHint || !createdAt) return [];
    const revokedAt = value.revokedAt === null || value.revokedAt === undefined
      ? null
      : nonEmptyString(value.revokedAt);
    if (value.revokedAt !== null && value.revokedAt !== undefined && !revokedAt) return [];
    return [{ id, sha256, keyHint, createdAt, revokedAt }];
  });
}

function toPublicCredential(credential: StoredIntegrationCredential): PublicIntegrationCredential {
  return {
    id: credential.id,
    keyHint: credential.keyHint,
    createdAt: credential.createdAt,
  };
}

function credentialHint(value: string): string {
  return `${value.slice(0, 7)}…${value.slice(-4)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}
