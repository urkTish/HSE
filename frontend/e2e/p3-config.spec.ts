import { expect, test } from "./fixtures/test";
import { apiAs, login, uid, USERS } from "./helpers";
import { pickMulti, projectIds } from "./p2-helpers";

/** Phase 3 configuration: zone PTW profile floors (AC1), issuer appointments (AC2), PTW settings ranges (AC9), SIMOPS rule floors (AC50). */

test("AC1 a new taxiway zone requires a permit for all work and the officer cannot loosen it", async ({ page }) => {
  const api = await apiAs(USERS.faisal);
  const ids = await projectIds(api);
  const code = `Z-TWY-${uid()}`;
  const res = await api.post(`/api/v1/sites/${ids.site("S-AIR")}/zones`, {
    data: {
      code,
      name_en: `Taxiway ${code}`,
      name_ar: "ممر اختبار",
      zone_type: "airside",
      airside: { airside_area: "taxiway", in_movement_area: true, escort_required: true, adp_required: true },
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();

  await login(page, USERS.noura);
  await page.goto("/en/ptw-setup/zones");
  await page.getByTestId("zone-item").filter({ hasText: code }).click();
  const card = page.getByTestId("zone-ptw-profile");
  const box = card.getByTestId("zp-permit-required");
  await expect(box).toBeChecked();
  await box.uncheck();
  await card.getByTestId("save-zone-profile").click();
  await expect(card.getByTestId("form-error")).toHaveAttribute("data-code", "PROFILE_LOOSENING");
});

test("AC2 only the HSE Manager can appoint a permit issuer", async ({ page }) => {
  await login(page, USERS.noura);
  await page.goto("/en/ptw-appointments");
  await page.getByTestId("new-appointment").click();
  const fn = page.getByTestId("ap-function");
  await expect(fn.locator("option[value=area_authority]")).toBeAttached();
  await expect(fn.locator("option[value=issuer]")).toHaveCount(0);

  // The API refuses it as well (403), whatever the UI shows.
  const officer = await apiAs(USERS.noura);
  const ids = await projectIds(officer);
  const khalid = await (await officer.get(`/api/v1/users?q=${USERS.khalid}`)).json() as { items: { id: string }[] };
  const r = await officer.post(`/api/v1/projects/${ids.pid}/ptw-appointments`, {
    data: { function: "issuer", holder_user_id: khalid.items[0]?.id, permit_types: ["general"], site_ids: [ids.site("S-LAND")], basis: "e2e officer attempt", valid_from: "2026-10-01", valid_to: "2027-09-30" },
  });
  expect(r.status()).toBe(403);
});

test("AC2 the HSE Manager creates an issuer appointment and it is active and audited", async ({ page }) => {
  await login(page, USERS.faisal);
  await page.goto("/en/ptw-appointments");
  await page.getByTestId("new-appointment").click();
  await page.getByTestId("ap-function").selectOption("issuer");
  const user = page.getByTestId("ap-user");
  const opt = user.locator("option", { hasText: "Khalid" }).first();
  await expect(opt).toBeAttached();
  await user.selectOption((await opt.getAttribute("value")) ?? "");
  await pickMulti(page, "ap-types", [/radiography/i]);
  await pickMulti(page, "ap-sites", [/S-LAND/]);
  await page.getByTestId("ap-basis").fill(`e2e issuer appointment ${uid()}`);
  await page.getByTestId("ap-to").fill("2027-09-30");
  await page.getByTestId("save-appointment").click();
  await expect(page).toHaveURL(/\/ptw-appointments\/[0-9a-f-]{36}/);
  await expect(page.getByTestId("appointment-status")).toHaveAttribute("data-status", "active");
  // Audited: the audit log has the create entry (the history panel needs Phase 3 support in /history, see PROGRESS).
  const id = page.url().split("/").pop() ?? "";
  const api = await apiAs(USERS.faisal);
  const log = (await (await api.get(`/api/v1/audit-log?entity_type=ptw_appointment&entity_id=${id}`)).json()) as { items: { action: string }[] };
  expect(log.items.length).toBeGreaterThan(0);
});

test("AC9 permit type durations outside the allowed range are refused, inside are saved", async ({ page }) => {
  await login(page, USERS.faisal);
  await page.goto("/en/ptw-setup/settings");
  const settings = page.getByTestId("ptw-settings");
  const hot = settings.getByTestId("ps-dur-hot_work");
  const original = await hot.inputValue();
  await hot.fill("8");
  await settings.getByTestId("save-ptw-settings").click();
  await expect(settings.getByTestId("form-error")).toBeVisible();
  await hot.fill("7");
  await settings.getByTestId("save-ptw-settings").click();
  await expect(settings.getByTestId("form-error")).toHaveCount(0);
  await expect(page.getByText(/saved/i).first()).toBeVisible();
  // Put the seeded value back so later permit specs see the spec defaults.
  await page.reload();
  await settings.getByTestId("ps-dur-hot_work").fill(original);
  await settings.getByTestId("save-ptw-settings").click();
  await expect(settings.getByTestId("form-error")).toHaveCount(0);
  await expect(settings.getByTestId("ps-dur-hot_work")).toHaveValue(original);
});

test("AC50 a mandatory SIMOPS rule cannot be deleted; tightening SM-R02 is saved", async ({ page }) => {
  await login(page, USERS.faisal);
  await page.goto("/en/ptw-setup/simops-rules");
  const r01 = page.getByTestId("simops-rule-row").filter({ hasText: "SM-R01" });
  await r01.getByTestId("delete-simops-rule").click();
  await page.getByTestId("step-confirm").click();
  await expect(page.getByRole("dialog").getByTestId("form-error")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

  const r02 = page.getByTestId("simops-rule-row").filter({ hasText: "SM-R02" });
  await r02.getByTestId("edit-simops-rule").click();
  await page.getByTestId("sr-threshold").fill("20.0");
  await page.getByTestId("save-simops-rule").click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(r02).toContainText("20");
});
