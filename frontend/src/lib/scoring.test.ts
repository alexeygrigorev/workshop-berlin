import { describe, expect, it } from "vitest";
import { moveChoice, placeChoice, toggleChoice } from "./scoring";

describe("tap to rank", () => {
  it("fills ranks in tap order and refuses a fourth", () => {
    let sel: string[] = [];
    for (const id of ["a", "b", "c"]) sel = toggleChoice(sel, id).next;
    expect(sel).toEqual(["a", "b", "c"]);
    const r = toggleChoice(sel, "d");
    expect(r.full).toBe(true);
    expect(r.next).toEqual(["a", "b", "c"]);
  });
  it("removing a pick closes the gap", () => {
    expect(toggleChoice(["a", "b", "c"], "a").next).toEqual(["b", "c"]);
  });
  it("moves picks up and down", () => {
    expect(moveChoice(["a", "b", "c"], 2, -1)).toEqual(["a", "c", "b"]);
    expect(moveChoice(["a", "b"], 0, -1)).toEqual(["a", "b"]);
  });
  it("places a pick at an explicit rank, shifting others down", () => {
    expect(placeChoice(["a", "b"], "c", 0)).toEqual({ next: ["c", "a", "b"], dropped: null });
    expect(placeChoice(["a", "b", "c"], "d", 1)).toEqual({ next: ["a", "d", "b"], dropped: "c" });
    expect(placeChoice(["a", "b", "c"], "c", 0)).toEqual({ next: ["c", "a", "b"], dropped: null });
    expect(placeChoice(["a"], "b", 2)).toEqual({ next: ["a", "b"], dropped: null });
    expect(placeChoice(["a", "b"], "b", 1)).toEqual({ next: ["a"], dropped: null });
  });
});
