import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { assertSafeLiveTarget } from "./live-target-safety";

test.skip(!process.env.LIVE_PASSWORD_RESET_ACCEPTANCE,"requires the migrated local backend");
test.setTimeout(180_000);

test("live forgot-password and single-use update-password journey",async({page,request})=>{
  await assertSafeLiveTarget(request);
  const email=`live-reset-${Date.now()}@example.com`;const mobile=`7${String(Date.now()).slice(-9)}`;
  const oldPassword="StrongPassword123!";const newPassword="NewStrongPassword456!";
  const outboxPath=process.env.PASSWORD_RESET_OUTBOX_PATH;const invitationCode=process.env.LIVE_PASSWORD_RESET_INVITE??process.env.LIVE_REGISTRATION_INVITE;
  if(!outboxPath||!invitationCode)throw new Error("Reset outbox and invitation code are required");
  await page.goto("/register");await page.getByLabel("Name").fill("Live Reset Learner");await page.getByLabel("Email").fill(email);await page.getByLabel("Indian mobile number").fill(mobile);await page.getByLabel("Password").fill(oldPassword);await page.getByLabel("Closed-beta invitation code (if provided)").fill(invitationCode);await page.getByLabel(/Terms and Privacy/).check();await page.getByRole("button",{name:"Create learner account"}).click();await expect(page).toHaveURL(/\/onboarding$/);
  await page.getByRole("radio",{name:/Ananya/}).click();await page.getByRole("button",{name:"Continue with my tutor"}).click();await page.getByRole("button",{name:"Log out"}).click();
  await page.getByRole("button",{name:"Forgot password?"}).click();await page.getByLabel("Email").fill(email);await page.getByRole("button",{name:"Send verification code"}).click();await expect(page).toHaveURL(/\/reset-password$/);
  const delivery=(await readFile(outboxPath,"utf8")).trim().split("\n").map(line=>JSON.parse(line) as {recipient:string;verification_code:string}).reverse().find(item=>item.recipient===email);if(!delivery)throw new Error("Development reset delivery was not found");
  await page.getByLabel("Six-digit verification code").fill("000000");await page.getByLabel("New password").fill(newPassword);await page.getByRole("button",{name:"Update password"}).click();await expect(page.getByRole("status")).toContainText("invalid or expired");
  await page.getByLabel("Six-digit verification code").fill(delivery.verification_code);await page.getByRole("button",{name:"Update password"}).click();await expect(page.getByRole("status")).toContainText("has been updated");
  await page.goto("/reset-password");await page.getByLabel("Email").fill(email);await page.getByLabel("Six-digit verification code").fill(delivery.verification_code);await page.getByLabel("New password").fill("AnotherStrongPassword789!");await page.getByRole("button",{name:"Update password"}).click();await expect(page.getByRole("status")).toContainText("invalid or expired");
  await page.goto("/login");await page.getByLabel("Email").fill(email);await page.getByLabel("Password").fill(oldPassword);await page.getByRole("button",{name:"Login"}).click();await expect(page.getByRole("alert")).toContainText("could not sign you in");await page.getByLabel("Password").fill(newPassword);await page.getByRole("button",{name:"Login"}).click();await expect(page).toHaveURL(/\/app\/dashboard$/);
});
