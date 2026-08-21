import { createHash } from "node:crypto";

import { describe, expect, it } from "vitest";

import {
  LEGACY_INTEGRATION_CREDENTIAL_ID,
  activeIntegrationCredentials,
  appendIntegrationCredential,
  issueIntegrationCredential,
  publicIntegrationCredentials,
  revokeIntegrationCredentialDigest,
} from "./integration-credentials.js";

const createdAt = new Date("2026-08-20T01:02:03.000Z");

describe("Integration credential verification", () => {
  it("issues a one-time value while keeping digests out of the public credential", () => {
    const issued = issueIntegrationCredential(createdAt);

    expect(issued.value).toMatch(/^tg_/);
    expect(issued.stored.sha256).toBe(createHash("sha256").update(issued.value).digest("hex"));
    expect(issued.publicCredential).toEqual({
      id: issued.stored.id,
      keyHint: issued.stored.keyHint,
      createdAt: createdAt.toISOString(),
    });
    expect(JSON.stringify(issued.publicCredential)).not.toContain(issued.stored.sha256);
  });

  it("projects legacy and structured digests without exposing either digest", () => {
    const legacyDigest = "a".repeat(64);
    const structuredDigest = "b".repeat(64);
    const verification = {
      credentialSha256: legacyDigest,
      credentials: [{
        id: "credential-2",
        sha256: structuredDigest,
        keyHint: "tg_next…abcd",
        createdAt: "2026-08-20T02:00:00.000Z",
        revokedAt: null,
      }],
    };

    expect(publicIntegrationCredentials(verification, createdAt)).toEqual([
      { id: "credential-2", keyHint: "tg_next…abcd", createdAt: "2026-08-20T02:00:00.000Z" },
      { id: LEGACY_INTEGRATION_CREDENTIAL_ID, keyHint: "legacy credential", createdAt: createdAt.toISOString() },
    ]);
    expect(JSON.stringify(publicIntegrationCredentials(verification, createdAt))).not.toContain(legacyDigest);
    expect(JSON.stringify(publicIntegrationCredentials(verification, createdAt))).not.toContain(structuredDigest);
  });

  it("retains revoked records internally and excludes them from active credentials", () => {
    const issued = issueIntegrationCredential(createdAt);
    const verification = appendIntegrationCredential({}, issued.stored);
    const revoked = revokeIntegrationCredentialDigest(verification, issued.stored.id, new Date("2026-08-20T03:00:00.000Z"));

    expect(revoked).not.toBeNull();
    expect(activeIntegrationCredentials(revoked ?? {}, createdAt)).toEqual([]);
    expect(revoked).toMatchObject({
      credentials: [expect.objectContaining({ id: issued.stored.id, revokedAt: "2026-08-20T03:00:00.000Z" })],
    });
  });

  it("removes only the legacy digest when revoking a legacy credential", () => {
    const verification = { credentialSha256: "a".repeat(64), provider: "kept" };
    expect(revokeIntegrationCredentialDigest(verification, LEGACY_INTEGRATION_CREDENTIAL_ID, createdAt))
      .toEqual({ provider: "kept" });
    expect(revokeIntegrationCredentialDigest({}, LEGACY_INTEGRATION_CREDENTIAL_ID, createdAt)).toBeNull();
  });
});
