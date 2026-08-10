import { expect, test } from "@playwright/test";
import { assertSafeLiveTarget } from "./live-target-safety";

test.skip(!process.env.LIVE_COMPLETE_JOURNEY, "requires the isolated deterministic acceptance backend");
test.setTimeout(240_000);

test("new learner completes a structured lesson and can resume after login", async ({ page, request }) => {
  await assertSafeLiveTarget(request);
  const invitationCode = process.env.LIVE_REGISTRATION_INVITE;
  if (!invitationCode) throw new Error("LIVE_REGISTRATION_INVITE is required");
  const email = `journey-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  const password = "StrongPassword123!";

  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = function play() {
      this.dispatchEvent(new Event("playing"));
      return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = function pause() { this.dispatchEvent(new Event("pause")); };
  });

  await page.goto("/register");
  await page.getByLabel("Name").fill("Acceptance Learner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByLabel("Closed-beta invitation code (if provided)").fill(invitationCode);
  await page.getByLabel(/accept the Terms/).check();
  await page.getByRole("button", { name: "Create learner account" }).click();
  await expect(page).toHaveURL(/\/onboarding$/, { timeout: 30_000 });

  await page.getByRole("radio", { name: /Ananya/ }).click();
  await page.getByLabel(/English \+ Telugu explanation/).check();
  await page.getByRole("button", { name: "Continue with my tutor" }).click();
  await expect(page).toHaveURL(/\/app\/dashboard$/, { timeout: 30_000 });

  await page.getByRole("button", { name: "Daily lesson" }).click();
  await expect(page.getByRole("button", { name: "Begin lesson" })).toBeVisible({ timeout: 30_000 });
  const firstLessonTitle = await page.getByRole("heading", { level: 1 }).textContent();
  expect(firstLessonTitle).toBeTruthy();
  await page.getByRole("button", { name: "Begin lesson" }).click();
  await expect(page).toHaveURL(/\/app\/conversation$/);
  await expect(page.getByText(firstLessonTitle!, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start conversation" })).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("button", { name: "Start conversation" }).click();
  await page.getByRole("button", { name: "Text mode" }).click();

  for (const message of ["My morning routine starts with tea.", "Then I practise English for ten minutes."]) {
    await page.getByLabel("Your message").fill(message);
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.locator(".text-conversation-history p").filter({ hasText: message })).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 30_000 });
  }

  await expect(page.getByText("2 of 2 practice responses completed.")).toBeVisible();
  await page.getByRole("button", { name: "Complete lesson" }).click();
  await expect(page).toHaveURL(/\/app\/daily-lesson$/, { timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Begin lesson" })).toBeVisible();
  const nextLessonTitle = await page.getByRole("heading", { level: 1 }).textContent();
  expect(nextLessonTitle).not.toBe(firstLessonTitle);

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/, { timeout: 30_000 });
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Login" }).click();
  await expect(page).toHaveURL(/\/app\/dashboard$/, { timeout: 30_000 });
  await page.getByRole("button", { name: "Daily lesson" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(nextLessonTitle!);
});
