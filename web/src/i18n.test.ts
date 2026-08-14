import { describe, expect, it } from "vitest";

describe("Policy Library jurisdiction translations", () => {
  it("uses natural Simplified Chinese labels", async () => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: () => null,
        setItem: () => undefined,
      },
    });
    const { default: i18n } = await import("./i18n");
    const t = i18n.getFixedT("zh-CN");

    expect(t("policyLibrary.tagNamespaces.jurisdiction")).toBe("适用地区");
    expect(t("policyLibrary.jurisdictions.au")).toBe("澳大利亚");
    expect(t("policyLibrary.jurisdictions.eu")).toBe("欧盟");
    expect(t("policyLibrary.jurisdictions.sg")).toBe("新加坡");
    expect(t("policyLibrary.jurisdictions.uae")).toBe("阿联酋");
  });
});
