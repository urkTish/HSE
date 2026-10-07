import { expect, test } from "@playwright/test";
import { login, uid, USERS } from "./helpers";
import { pickMulti, selectContaining } from "./p2-helpers";

/** "YYYY-MM-DDTHH:mm" for a UTC datetime-local input, `days` from now at 04:00Z. */
function utcInput(days: number, hour = 4): string {
  const d = new Date(Date.now() + days * 86400_000);
  d.setUTCHours(hour, 0, 0, 0);
  return d.toISOString().slice(0, 16);
}

function isoDay(days: number): string {
  return new Date(Date.now() + days * 86400_000).toISOString().slice(0, 10);
}

test.describe.serial("Phase 2 — NOTAM works requests and obstacle clearances", () => {
  let notamUrl = "";
  let ntmNo = "";

  test("AC41 (UI): a request inside the lead time needs a justification and is flagged late; times are UTC", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/notams/new");
    await pickMulti(page, "nf-zones", [/Z-TWB/]);
    await pickMulti(page, "nf-impact", [/Taxiway closure/i]);
    await page.locator("#nf-desc-en").fill(`Taxiway B shoulder works ${uid()}`);
    await page.locator("#nf-desc-ar").fill("أعمال كتف الممر B");
    await page.locator("#nf-start").fill(utcInput(2));
    await page.locator("#nf-end").fill(utcInput(4, 13));
    await page.locator("#nf-schedule").fill("DAILY 0400-1300");
    await page.getByTestId("save-notam").click();
    await expect(page).toHaveURL(/\/notams\/[0-9a-f-]{36}$/);
    notamUrl = new URL(page.url()).pathname.replace(/^\/en/, "");
    ntmNo = (await page.locator("h1").innerText()).trim();
    await expect(page.getByTestId("notam-utc").first()).toHaveCSS("direction", "ltr");

    await page.getByTestId("ntm-submit").click();
    const dlg = page.getByRole("dialog");
    await expect(dlg).toContainText(/justification/i);
    await expect(page.getByTestId("step-confirm")).toBeDisabled();
    await page.locator("#ntm-late").fill("Urgent repair after FOD damage found at inspection.");
    await page.getByTestId("step-confirm").click();
    await expect(page.getByTestId("notam-status")).toHaveAttribute("data-status", "submitted_to_ops");
    await expect(page.getByTestId("late-request")).toBeVisible();
  });

  test("NT: Airport Ops records the request to AIS and the issued NOTAM", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto(`/en${notamUrl}`);
    await page.getByTestId("ntm-forward").click();
    await page.getByTestId("step-confirm").click();
    await expect(page.getByTestId("notam-status")).toHaveAttribute("data-status", "requested_from_ais");
    await page.getByTestId("ntm-issue").click();
    await page.locator("#in-num").fill(`A${Math.floor(1000 + Math.random() * 8999)}/26`);
    await page.locator("#in-from").fill(utcInput(2));
    await page.locator("#in-to").fill(utcInput(4, 13));
    await page.getByTestId("issue-notam-confirm").click();
    await expect(page.getByTestId("notam-status")).toHaveAttribute("data-status", "issued");
  });

  test("AC42 (UI): the live preview shows top, penetration and reasons; approval without the required conditions is refused", async ({ page }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/obstacle-clearances/new");
    await page.locator("#of-type").selectOption("mobile_crane");
    await selectContaining(page.locator("#of-eng"), "GULFPAVE");
    await page.locator("#of-desc").fill("50 t mobile crane");
    await selectContaining(page.locator("#of-zone"), "Z-TWB");
    await page.locator("#of-loc").fill("TWY B shoulder, stand 21 side");
    await page.locator("#of-lat").fill("24.95812");
    await page.locator("#of-lng").fill("46.70321");
    await page.locator("#of-ground").fill("612.40");
    await page.locator("#of-height").fill("35");
    const ols = page.locator("#of-ols");
    if (await ols.count()) await ols.selectOption({ index: 1 });
    await page.locator("#of-ols-limit").fill("642.50");
    await page.locator("#of-from").fill(isoDay(40));
    await page.locator("#of-to").fill(isoDay(45));
    const preview = page.getByTestId("height-preview");
    await expect(preview).toHaveAttribute("data-required", "true");
    await expect(page.getByTestId("top-amsl")).toContainText("647.40");
    await expect(page.getByTestId("penetration")).toContainText("4.90");
    await expect(page.getByTestId("penetration")).toContainText("16.08");
    await expect(page.getByTestId("clearance-reasons")).toHaveAttribute("data-reasons", /ols_penetration/);
    await page.getByTestId("save-obstacle").click();
    await expect(page).toHaveURL(/\/obstacle-clearances\/[0-9a-f-]{36}$/);

    await page.getByTestId("obs-submit").click();
    await page.getByTestId("step-confirm").click();
    await expect(page.getByTestId("obstacle-status")).toHaveAttribute("data-status", "submitted");
    await page.getByTestId("obs-decide").click();
    await page.locator("#dc-decision").selectOption("approved_with_conditions");
    await page.locator("#dc-ref").fill(`GACA-OB-${uid()}`);
    await pickMulti(page, "dc-conds", [/Day marking/i]);
    await page.getByTestId("decision-confirm").click();
    await expect(page.getByRole("dialog").getByTestId("form-error")).toBeVisible();
    await pickMulti(page, "dc-conds", [/Obstruction light/i, /NOTAM/i]);
    // OB-7: a NOTAM-required condition needs the NOTAM request linked.
    await pickMulti(page, "dc-ntms", [ntmNo]);
    await page.getByTestId("decision-confirm").click();
    await expect(page.getByTestId("obstacle-status")).toHaveAttribute("data-status", "approved_with_conditions");
  });
});
