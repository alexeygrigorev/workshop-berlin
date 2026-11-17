import { expect, test } from "@playwright/test";

test("a restaurant added by Anna survives a page reload", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.push(`console.error: ${msg.text()}`);
  });
  page.on("pageerror", (err) => {
    // Known, benign app issue: the prerendered SPA shell (build:static) mismatches on the landing page "/",
    // so React logs hydration error #418 and recovers by client-rendering. Ignored for "/" only; anywhere
    // else (the actual scenario pages) it is still a failure.
    const onLanding = new URL(page.url()).pathname === "/";
    if (onLanding && /Minified React error #418/.test(err.message)) return;
    problems.push(`pageerror: ${err.message} @ ${page.url()}`);
  });

  const name = `E2E Bistro ${Date.now()}`;

  // Start page -> sign in
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in" }).first().click();
  await expect(page).toHaveURL(/\/auth$/);

  await page.getByLabel("Work email").fill("anna@example.com");
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  // Teams -> Design crew -> Restaurants
  await expect(page).toHaveURL(/\/teams$/);
  await page.getByRole("link", { name: /Design crew/ }).click();
  await page.getByRole("link", { name: "Restaurants", exact: true }).click();
  await expect(page).toHaveURL(/\/t\/[^/]+\/restaurants/);
  const list = page.getByRole("list").filter({ has: page.getByRole("button", { name: "Archive" }) });
  await expect(list).toBeVisible();
  await expect(list.getByText(name)).toHaveCount(0);

  // Add one
  await page.getByLabel("Name", { exact: true }).fill(name);
  await page.getByLabel("Cuisine").fill("Testing");
  await page.getByLabel("Address").fill("1 Persistence Street");
  await page.getByRole("button", { name: "Add restaurant" }).click();
  await expect(list.getByText(name, { exact: true })).toBeVisible();

  // Persisted: still there after a reload (comes back from backend + Postgres)
  await page.reload();
  await expect(list.getByText(name, { exact: true })).toBeVisible();

  // ...and after navigating away and back
  await page.goto("/teams");
  await page.getByRole("link", { name: /Design crew/ }).click();
  await page.getByRole("link", { name: "Restaurants", exact: true }).click();
  await expect(list.getByText(name, { exact: true })).toBeVisible();

  expect(problems, "browser console/page errors").toEqual([]);
});
