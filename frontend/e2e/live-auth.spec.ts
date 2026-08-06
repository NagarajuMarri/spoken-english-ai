import { expect, test } from "@playwright/test";

test.skip(!process.env.LIVE_AUTH_ACCEPTANCE, "requires the migrated local backend");
test.setTimeout(120_000);

test("live registration, logout, login, restoration, and safe rejection", async ({ page }) => {
  const email = "live-acceptance@example.com";
  const password = "StrongPassword123!";

  await page.goto("/register");
  await page.getByLabel("Name").fill("Live Acceptance");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create learner account" }).click();
  await expect(page).toHaveURL(/\/onboarding$/);

  await page.getByRole("radio", { name: /Ananya/ }).click();
  await page.getByRole("button", { name: "Continue with my tutor" }).click();
  await expect(page.getByText("Ready for today’s conversation?")).toBeVisible();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Login" }).click();
  await expect(page.getByText("Ready for today’s conversation?")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Ready for today’s conversation?")).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await page.getByRole("button", { name: "Create a new account" }).click();
  await page.getByLabel("Name").fill("Duplicate");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  const duplicate = page.waitForResponse((response) => response.url().endsWith("/auth/register"));
  await page.getByRole("button", { name: "Create learner account" }).click();
  expect((await duplicate).status()).toBe(409);
  await expect(page.getByRole("alert")).toContainText("could not sign you in");

  await page.getByRole("button", { name: "I already have an account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("WrongPassword123!");
  const invalid = page.waitForResponse((response) => response.url().endsWith("/auth/login"));
  await page.getByRole("button", { name: "Login" }).click();
  expect((await invalid).status()).toBe(401);
  await expect(page.getByRole("alert")).toContainText("could not sign you in");
});
