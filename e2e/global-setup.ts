import { BASE_URL, PREBUILT_IMAGE, REUSE_URL, assertPrebuiltImage, assertRunningImage, compose } from "./stack";

async function waitForHealth(timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;
  let last = "";
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE_URL}/v1/health`);
      if (res.ok) return;
      last = `HTTP ${res.status}`;
    } catch (e) {
      last = String(e);
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`${BASE_URL}/v1/health not healthy after ${timeoutMs}ms (${last})`);
}

export default async function globalSetup() {
  if (!REUSE_URL) {
    // Start from a clean slate (stale stack from a killed run), then start. With WSWE_IMAGE set (CI) the
    // prebuilt image is used as is; otherwise build it.
    compose(["down", "-v", "--remove-orphans"]);
    if (PREBUILT_IMAGE) {
      const imageId = assertPrebuiltImage(); // throws (never builds) if missing or not the expected image
      compose(["up", "-d", "--no-build", "--wait"]);
      assertRunningImage(imageId);
    } else {
      compose(["up", "-d", "--build", "--wait"]);
    }
  }
  await waitForHealth(60_000);
  // Playwright runs the returned function after all tests, including failed ones.
  return async () => {
    if (!REUSE_URL) compose(["down", "-v", "--remove-orphans"]);
  };
}
