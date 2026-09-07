import { beforeEach, describe, expect, it, vi } from "vitest";

const { signInWithEmail, getSession } = vi.hoisted(() => ({
  signInWithEmail: vi.fn(),
  getSession: vi.fn(),
}));

vi.mock("@/lib/better-auth", () => ({
  authClient: {
    signIn: { email: signInWithEmail },
    getSession,
  },
}));

import { getAuthStatus, login } from "@/lib/identity-api";

const signedInUser = {
  id: "admin-id",
  name: "Administrator",
  email: "admin@tasklattice.local",
  role: "admin",
  banned: false,
  preferredLanguage: "zh-CN",
  createdAt: "2026-08-20T00:00:00.000Z",
  updatedAt: "2026-08-20T00:00:00.000Z",
};

describe("identity login", () => {
  beforeEach(() => {
    getSession.mockReset();
    signInWithEmail.mockReset();
    signInWithEmail.mockResolvedValue({ data: { user: signedInUser }, error: null });
  });

  it("checks current session state rather than a stale signed cookie", async () => {
    getSession.mockResolvedValue({ data: null, error: null });
    expect(await getAuthStatus()).toEqual({ authenticated: false, user: null });
    expect(getSession).toHaveBeenCalledWith({ query: { disableCookieCache: true } });
  });

  it("maps the admin username alias to the internal Better Auth email", async () => {
    await login({ email: " ADMIN ", password: "admin" });

    expect(signInWithEmail).toHaveBeenCalledWith({
      email: "admin@tasklattice.local",
      password: "admin",
    });
  });

  it("passes an explicit email to Better Auth after normalizing it", async () => {
    await login({ email: " Admin@Example.COM ", password: "a-secure-password" });

    expect(signInWithEmail).toHaveBeenCalledWith({
      email: "admin@example.com",
      password: "a-secure-password",
    });
  });
});
