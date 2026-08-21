import { describe, expect, it, vi } from "vitest";

import type { ControllerConfig } from "../config.js";
import type { ControllerDatabase } from "../db/client.js";
import { ControlPlaneService } from "./control-plane.js";

describe("Runner registration removal", () => {
  it("keeps the GuardRails 0 desired capacity at two or more", async () => {
    const db = { transaction: vi.fn() } as unknown as ControllerDatabase;
    const update = new ControlPlaneService(db, {} as ControllerConfig).updateRunnerPool({
      id: "default",
      desiredReplicas: 1,
      safeRpsPerRunner: 50,
      maxConcurrencyPerRunner: 64,
      actorId: "admin-1",
    });

    await expect(update).rejects.toMatchObject({
      status: 422,
      detail: { minimumDesiredReplicas: 2 },
    });
    expect(db.transaction).not.toHaveBeenCalled();
  });

  it("removes only the current registration and records immutable audit context", async () => {
    const removed = {
      runnerId: "runner-offline",
      bootId: "boot-1",
      poolId: "default",
      status: "offline",
      lastHeartbeatAt: new Date("2026-08-20T10:00:00.000Z"),
      disconnectedAt: new Date("2026-08-20T10:00:30.000Z"),
    };
    const returning = vi.fn().mockResolvedValue([removed]);
    const deleteWhere = vi.fn(() => ({ returning }));
    const deleteRow = vi.fn(() => ({ where: deleteWhere }));
    const auditValues = vi.fn().mockResolvedValue(undefined);
    const insert = vi.fn(() => ({ values: auditValues }));
    const tx = { delete: deleteRow, insert };
    const db = {
      transaction: vi.fn(async (callback: (transaction: typeof tx) => Promise<void>) => callback(tx)),
    } as unknown as ControllerDatabase;

    await new ControlPlaneService(db, {} as ControllerConfig).removeRunnerInstance({
      runnerId: removed.runnerId,
      actorId: "admin-1",
    });

    expect(deleteRow).toHaveBeenCalledOnce();
    expect(insert).toHaveBeenCalledOnce();
    expect(auditValues).toHaveBeenCalledWith(expect.objectContaining({
      kind: "runner_instance.removed",
      actorId: "admin-1",
      resourceType: "runner_instance",
      resourceId: removed.runnerId,
      detail: {
        bootId: removed.bootId,
        poolId: removed.poolId,
        lastHeartbeatAt: "2026-08-20T10:00:00.000Z",
        disconnectedAt: "2026-08-20T10:00:30.000Z",
      },
    }));
  });

  it("rejects removing a Runner that has reconnected", async () => {
    const returning = vi.fn().mockResolvedValue([]);
    const tx = {
      delete: vi.fn(() => ({ where: vi.fn(() => ({ returning })) })),
      select: vi.fn(() => ({
        from: vi.fn(() => ({
          where: vi.fn(() => ({
            limit: vi.fn().mockResolvedValue([{ status: "ready" }]),
          })),
        })),
      })),
      insert: vi.fn(),
    };
    const db = {
      transaction: vi.fn(async (callback: (transaction: typeof tx) => Promise<void>) => callback(tx)),
    } as unknown as ControllerDatabase;

    const removal = new ControlPlaneService(db, {} as ControllerConfig).removeRunnerInstance({
      runnerId: "runner-ready",
      actorId: "admin-1",
    });

    await expect(removal).rejects.toMatchObject({
      code: "runner_not_offline",
      status: 409,
    });
    expect(tx.insert).not.toHaveBeenCalled();
  });
});
