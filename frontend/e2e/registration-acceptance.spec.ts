import { expect, test } from "@playwright/test";
import { assertSafeLiveTarget } from "./live-target-safety";

test.skip(!process.env.LIVE_REGISTRATION_ACCEPTANCE, "requires the migrated Feature 2 backend");

function uniqueEmail(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

function invitationCode() {
  const value = process.env.LIVE_REGISTRATION_INVITE;
  if (!value) throw new Error("LIVE_REGISTRATION_INVITE is required");
  return value;
}

test("closed-beta registration journey", async ({ page, request }) => {
  await assertSafeLiveTarget(request);
  const email = uniqueEmail("browser-feature2");
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "Start practising" })).toBeVisible();
  await expect(page.getByLabel("Closed-beta invitation code (if provided)")).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.getByRole("heading", { name: "Start practising" })).toBeVisible();

  const submit = page.getByRole("button", { name: "Create learner account" });
  await page.getByLabel("Name").fill("Browser Learner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("StrongPassword123!");
  await page.getByLabel("Closed-beta invitation code (if provided)").fill(invitationCode());
  await submit.click();
  await expect(page.getByLabel(/Terms and Privacy/)).toHaveJSProperty("validity.valueMissing", true);

  await page.getByLabel(/Terms and Privacy/).check();
  const accepted = page.waitForResponse(response => response.url().endsWith("/auth/register"));
  await submit.click();
  expect((await accepted).status()).toBe(201);
  await expect(page).toHaveURL(/\/onboarding$/);
});

test("waitlist, duplicate, malformed email, and password messaging", async ({ page, request }) => {
  await assertSafeLiveTarget(request);
  const waitlistEmail = uniqueEmail("browser-waitlist");
  const duplicateEmail = uniqueEmail("browser-duplicate");
  await page.goto("/register");
  await page.getByLabel("Name").fill("Waiting Browser Learner");
  await page.getByLabel("Email").fill(waitlistEmail);
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

  const seeded = await page.request.post("/api/v1/auth/register", {
    data: {
      display_name: "Accepted Browser Learner",
      email: duplicateEmail,
      password: "StrongPassword123!",
      invitation_code: invitationCode(),
      terms_privacy_accepted: true,
    },
  });
  expect(seeded.status()).toBe(201);

  await page.getByLabel("Email").fill(duplicateEmail);
  await page.getByLabel("Password").fill("StrongPassword123!");
  await page.getByLabel("Closed-beta invitation code (if provided)").fill(invitationCode());
  const duplicate = page.waitForResponse(response => response.url().endsWith("/auth/register"));
  await page.getByRole("button", { name: "Create learner account" }).click();
  expect((await duplicate).status()).toBe(409);
  await expect(page.getByRole("alert")).toContainText("An account with this email exists.");
});
