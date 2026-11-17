import { describe, expect, it } from "vitest";
import { moveChoice, placeChoice, tally, toggleChoice } from "./scoring";

const c = [
  { id: "a", name: "Alpha" },
  { id: "b", name: "Bravo" },
  { id: "c", name: "Charlie" },
];

describe("scoring", () => {
  it("awards 3/2/1 points for 1st/2nd/3rd", () => {
    const s = tally(c, [{ choices: ["a", "b", "c"] }]);
    expect(s.map((r) => [r.restaurant_id, r.score])).toEqual([["a", 3], ["b", 2], ["c", 1]]);
  });
  it("partial ballots give no points to missing ranks", () => {
    const s = tally(c, [{ choices: ["b"] }]);
    expect(s.find((r) => r.restaurant_id === "b")!.score).toBe(3);
    expect(s.find((r) => r.restaurant_id === "a")!.score).toBe(0);
  });
  it("ties on points are ordered by first-place votes", () => {
    // a: 3+1 = 4 (one first), b: 2+2 = 4 (zero first)
    const s = tally(c, [{ choices: ["a", "b"] }, { choices: ["c", "b", "a"] }]);
    expect(s[0].restaurant_id).toBe("a");
  });
});

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
