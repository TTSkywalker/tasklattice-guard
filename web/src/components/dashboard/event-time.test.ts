import { describe, expect, it } from "vitest";

import { formatEventTimestamp } from "@/components/dashboard/event-time";

describe("formatEventTimestamp", () => {
  it("keeps second and millisecond precision for dense runtime streams", () => {
    const formatted = formatEventTimestamp("2026-08-14T03:17:49.123456+00:00", "en-US");

    expect(formatted.time).toMatch(/^\d{2}:\d{2}:49\.123$/);
    expect(formatted.date).toContain("14");
  });
});
