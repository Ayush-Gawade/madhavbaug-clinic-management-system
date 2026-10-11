import { beforeEach, describe, expect, it } from "vitest";

import { tokenStore } from "./tokenStore";

describe("tokenStore", () => {
  beforeEach(() => {
    tokenStore.clear();
  });

  it("starts empty", () => {
    expect(tokenStore.getAccess()).toBeNull();
    expect(tokenStore.getRefresh()).toBeNull();
  });

  it("stores and returns tokens", () => {
    tokenStore.set("access-value", "refresh-value");
    expect(tokenStore.getAccess()).toBe("access-value");
    expect(tokenStore.getRefresh()).toBe("refresh-value");
  });

  it("clears tokens", () => {
    tokenStore.set("a", "b");
    tokenStore.clear();
    expect(tokenStore.getAccess()).toBeNull();
    expect(tokenStore.getRefresh()).toBeNull();
  });
});
