import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test.skip(!process.env.LIVE_PASSWORD_RESET_ACCEPTANCE, "requires the migrated Feature 2 backend");
test.setTimeout(180_000);

test("live forgot-password and single-use update-password journey", async ({ page }) => {
  const email = process.env.LIVE_PASSWORD_RESET_EMAIL ?? "live-reset@example.com";
  const oldPassword = "StrongPassword123!";
  const newPassword = "NewStrongPassword456!";
  const outboxPath = process.env.PASSWORD_RESET_OUTBOX_PATH;
  if (!outboxPath) throw new Error("PASSWORD_RESET_OUTBOX_PATH is required");

  await page.goto("/register");
  await page.getByLabel("Name").fill("Live Reset Learner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(oldPassword);
  await page.getByLabel("Closed-beta invitation code (if provided)").fill(process.env.LIVE_PASSWORD_RESET_INVITE ?? "");
  await page.getByLabel(/Terms and Privacy/).check();
  await page.getByRole("button", {name:"Create learner account"}).click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await page.getByRole("radio", {name:/Ananya/}).click();
  await page.getByRole("button", {name:"Continue with my tutor"}).click();
  await expect(page).toHaveURL(/\/app\/dashboard$/);
  await page.getByRole("button", {name:"Log out"}).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByRole("button", {name:"Forgot password?"}).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", {name:"Send reset instructions"}).click();
  await expect(page.getByRole("status")).toContainText("If an account matches");

  const lines = (await readFile(outboxPath, "utf8")).trim().split("\n");
  const delivery = lines.map(line=>JSON.parse(line) as {recipient:string;reset_url:string}).reverse()
    .find(item=>item.recipient===email);
  if (!delivery) throw new Error("Development reset delivery was not found");
  await page.goto(delivery.reset_url);
  await expect(page.getByLabel("New password")).toBeVisible();
  await page.getByLabel("New password").fill(newPassword);
  await page.getByRole("button", {name:"Update password"}).click();
  await expect(page.getByRole("status")).toContainText("has been updated");

  await page.goto(delivery.reset_url);
  await expect(page.getByRole("alert")).toContainText("already been used");
  await page.getByRole("button", {name:"Back to login"}).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(oldPassword);
  await page.getByRole("button", {name:"Login"}).click();
  await expect(page.getByRole("alert")).toContainText("could not sign you in");
  await page.getByLabel("Password").fill(newPassword);
  await page.getByRole("button", {name:"Login"}).click();
  await expect(page).toHaveURL(/\/app\/dashboard$/);
});
