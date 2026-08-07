import { expect, test } from "@playwright/test";

test.skip(!process.env.LIVE_REGISTRATION_ACCEPTANCE, "requires the migrated Feature 2 backend");

test("closed-beta registration journey", async ({ page }) => {
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "Start practising" })).toBeVisible();
  await expect(page.getByLabel("Closed-beta invitation code (if provided)")).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.getByRole("heading", { name: "Start practising" })).toBeVisible();

  const submit = page.getByRole("button", { name: "Create learner account" });
  await page.getByLabel("Name").fill("Browser Learner");
  await page.getByLabel("Email").fill("browser-feature2-20260807@example.com");
  await page.getByLabel("Password").fill("StrongPassword123!");
  await page.getByLabel("Closed-beta invitation code (if provided)").fill("BETA-ACCEPT-2026");
  await submit.click();
  await expect(page.getByLabel(/Terms and Privacy/)).toHaveJSProperty("validity.valueMissing", true);

  await page.getByLabel(/Terms and Privacy/).check();
  const accepted = page.waitForResponse(response => response.url().endsWith("/auth/register"));
  await submit.click();
  expect((await accepted).status()).toBe(201);
  await expect(page).toHaveURL(/\/onboarding$/);
});

test("waitlist, duplicate, malformed email, and password messaging", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Waiting Browser Learner");
  await page.getByLabel("Email").fill("browser-waitlist-20260807@example.com");
  await page.getByLabel("Password").fill("StrongPassword123!");
  await page.getByLabel(/Terms and Privacy/).check();
  const waitlisted = page.waitForResponse(response => response.url().endsWith("/auth/register"));
  await page.getByRole("button", { name: "Create learner account" }).click();
  expect((await waitlisted).status()).toBe(403);
  await expect(page.getByRole("alert")).toContainText("beta waiting list");

  await page.getByLabel("Email").fill("malformed-email");
  await expect(page.getByLabel("Email")).toHaveJSProperty("validity.typeMismatch", true);
  await page.getByLabel("Password").fill("short");
  await expect(page.getByLabel("Password")).toHaveJSProperty("validity.tooShort", true);

  await page.getByLabel("Email").fill("accepted-20260807@example.com");
  await page.getByLabel("Password").fill("StrongPassword123!");
  await page.getByLabel("Closed-beta invitation code (if provided)").fill("BETA-ACCEPT-2026");
  const duplicate = page.waitForResponse(response => response.url().endsWith("/auth/register"));
  await page.getByRole("button", { name: "Create learner account" }).click();
  expect((await duplicate).status()).toBe(409);
  await expect(page.getByRole("alert")).toContainText("An account with this email exists.");
});
