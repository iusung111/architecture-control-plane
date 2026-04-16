import { describe, expect, it } from "vitest";
import { cycleStates, isReplanAllowed, isRetryAllowed, isTerminalState } from "../../src/domain/states";

describe("state guards", () => {
  it("allow retry and replan only from verification_failed", () => {
    expect(isRetryAllowed(cycleStates.VERIFICATION_FAILED)).toBe(true);
    expect(isReplanAllowed(cycleStates.VERIFICATION_FAILED)).toBe(true);
    expect(isRetryAllowed(cycleStates.TERMINALIZED)).toBe(false);
    expect(isReplanAllowed(cycleStates.HUMAN_APPROVAL_PENDING)).toBe(false);
  });

  it("detect terminal states", () => {
    expect(isTerminalState(cycleStates.TERMINALIZED)).toBe(true);
    expect(isTerminalState(cycleStates.TERMINAL_FAIL)).toBe(true);
    expect(isTerminalState(cycleStates.VERIFICATION_FAILED)).toBe(false);
  });
});
