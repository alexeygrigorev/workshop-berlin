import { useLayoutEffect, useRef } from "react";

/**
 * FLIP animation for a list whose items re-order: children with a `data-flip-id`
 * glide from their previous position to the new one instead of jumping.
 * Pass a key that changes whenever the order may have changed.
 */
export function useFlip<T extends HTMLElement>(orderKey: string) {
  const ref = useRef<T>(null);
  const prev = useRef(new Map<string, number>());

  useLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const next = new Map<string, number>();
    const origin = root.getBoundingClientRect().top; // relative to the list, so scrolling doesn't count as movement
    root.querySelectorAll<HTMLElement>("[data-flip-id]").forEach((el) => {
      const id = el.dataset["flipId"]!;
      const top = el.getBoundingClientRect().top - origin;
      next.set(id, top);
      const before = prev.current.get(id);
      if (reduce || before === undefined || before === top) return;
      el.style.transition = "none";
      el.style.transform = `translateY(${before - top}px)`;
      requestAnimationFrame(() => {
        el.style.transition = "transform 250ms ease-out";
        el.style.transform = "";
      });
    });
    prev.current = next;
  }, [orderKey]);

  return ref;
}
