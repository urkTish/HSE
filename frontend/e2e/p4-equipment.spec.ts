import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";
import { pickMulti, selectContaining } from "./p2-helpers";
import { certCheckReady, PDF, uploadInto, USERS4 } from "./p4-helpers";

/**
 * Equipment register → deployment → certificate (strictest-wins preview, review, verification) →
 * mobilisation, arrival inspection, EQ sticker and the field check (spec 4 §3.4–§3.6, §4.2–§4.4;
 * AC13, AC21, AC36, AC65 UI, AC71).
 */
test("equipment lifecycle: register, deploy, certify, verify, mobilise, sticker and check", async ({
  page,
}) => {
  test.setTimeout(300_000);
  const sfx = uid();
  const serial = `TESTSN-FL-${sfx}`;
  const tag = `FL-${sfx}`;
  const certNo = `AICC-EQ-TEST-26-${sfx}`;

  // ── Ahmed (RAWABI) registers a forklift after the duplicate lookup (EQ-1).
  await login(page, USERS.ahmed);
  await page.goto("/en/equipment");
  await page.getByTestId("new-equipment").click();
  await page.getByTestId("eq-manufacturer").fill("Toyota");
  await page.getByTestId("eq-serial").fill(serial);
  await page.getByTestId("eq-lookup").click();
  await expect(page.getByTestId("lookup-new")).toBeVisible();
  await page.getByTestId("eq-category").selectOption("forklift");
  await page.getByTestId("eq-model").fill("8FD30");
  await page.getByTestId("eq-year").fill("2021");
  await selectContaining(page.getByTestId("eq-owner"), "RAWABI");
  await page.getByTestId("eq-capacity").fill("3.000");
  await page.getByTestId("save-equipment").click();
  await expect(page).toHaveURL(/\/equipment\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("service-status").first()).toHaveAttribute(
    "data-status",
    "awaiting_certificate",
  );
  const itemUrl = new URL(page.url()).pathname;
  const eqNo =
    ((await page.locator("h1").first().textContent()) ?? "").match(
      /EQP-\d+/,
    )?.[0] ?? "";
  expect(eqNo).not.toBe("");

  // AC13: the same serial with different case and spacing is found by the lookup.
  await page.goto("/en/equipment");
  await page.getByTestId("new-equipment").click();
  await page.getByTestId("eq-manufacturer").fill(" TOYOTA ");
  await page
    .getByTestId("eq-serial")
    .fill(serial.toLowerCase().replace(/-/g, " - "));
  await page.getByTestId("eq-lookup").click();
  await expect(page.getByTestId("lookup-exists")).toBeVisible();
  await expect(page.getByTestId("save-equipment")).toBeDisabled();
  await page.keyboard.press("Escape");

  // Deployment on ANIA-EXP with a per-project tag.
  await page.goto("/en/equipment-deployments");
  await page.getByTestId("new-eq-deployment").click();
  await page.getByTestId("ed-equipment-search").fill(serial);
  await selectContaining(page.getByTestId("ed-equipment"), eqNo);
  await selectContaining(page.getByTestId("ed-engagement"), "RAWABI");
  await page.getByTestId("ed-tag").fill(tag);
  await pickMulti(page, "ed-sites", [/S-LAND/]);
  await page.getByTestId("save-eq-deployment").click();
  await expect(page).toHaveURL(/\/equipment-deployments\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("deployment-status")).toHaveAttribute(
    "data-status",
    "planned",
  );
  const depUrl = new URL(page.url()).pathname;

  // ── Noura records the TPI certificate; the server computes validity (the UI never does).
  await page.context().clearCookies();
  await login(page, USERS.noura);
  await page.goto("/en/equipment-certificates/new");
  await selectContaining(page.getByTestId("ec-tpi"), "AICC");
  await page.getByTestId("ec-cert-no").fill(certNo);
  await page.getByTestId("ec-type").selectOption("initial");
  await page.getByTestId("ec-inspected").fill("2026-09-30");
  await page.getByTestId("ec-issued").fill("2026-10-01");
  await page.getByTestId("ec-inspector").fill("E2E Inspector");
  await selectContaining(page.getByTestId("ln-equipment-0"), tag);
  await page.getByTestId("ln-serial-0").fill(serial);
  await page.getByTestId("ln-swl-0").fill("3.000");
  // Forklift interval 12 months → valid until 2027-09-29, limited by the category interval.
  const pv = page.getByTestId("ln-preview-0");
  await expect(pv.getByTestId("cert-limiting-factor")).toHaveAttribute(
    "data-factor",
    "category_interval",
    { timeout: 20_000 },
  );
  await expect(pv.getByTestId("cert-validity")).toHaveAttribute(
    "data-valid-until",
    "2027-09-29",
  );
  await page.getByTestId("save-eq-cert").click();
  await expect(page).toHaveURL(/\/equipment-certificates\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("cert-status").first()).toHaveAttribute(
    "data-status",
    "draft",
  );
  await uploadInto(page, "ec-scan", PDF());
  await page.getByTestId("cert-action-submitted").click();
  await page.getByTestId("cert-transition-confirm").click();
  await expect(page.getByTestId("cert-status").first()).toHaveAttribute(
    "data-status",
    "submitted",
  );
  // AC36: the submitter cannot accept her own certificate.
  await expect(page.getByTestId("cert-action-accepted")).toHaveCount(0);
  const certUrl = new URL(page.url()).pathname;

  // ── Faisal accepts and records the verification with evidence (VF-1/VF-2).
  await page.context().clearCookies();
  await login(page, USERS.faisal);
  await page.goto(certUrl);
  await page.getByTestId("cert-action-accepted").click();
  await page.getByTestId("cert-transition-confirm").click();
  await expect(page.getByTestId("cert-status").first()).toHaveAttribute(
    "data-status",
    "accepted",
  );
  await expect(page.getByTestId("verification-status").first()).toHaveAttribute(
    "data-status",
    "not_verified",
  );
  await page.getByTestId("record-verification").click();
  await page.getByTestId("vf-method").selectOption("tpi_portal");
  await page.getByTestId("vf-channel").fill("verify.aicc-test.example");
  await page.getByTestId("vf-reference").fill(`PORTAL-${sfx}`);
  await uploadInto(page, "vf-evidence", PDF("portal.pdf"));
  await page.getByTestId("verify-confirm").click();
  await expect(page.getByTestId("verification-status").first()).toHaveAttribute(
    "data-status",
    "verified",
  );
  await page.goto(itemUrl);
  await expect(page.getByTestId("service-status").first()).toHaveAttribute(
    "data-status",
    "in_service",
  );

  // ── Mobilisation, arrival and the arrival inspection (EM-2, EM-3).
  await page.goto(depUrl);
  await page.getByTestId("approve-mobilisation").click();
  await page.getByTestId("eq-deployment-confirm").click();
  await expect(page.getByTestId("deployment-status")).toHaveAttribute(
    "data-status",
    "approved",
  );
  await page.getByTestId("record-arrival").click();
  await page.getByTestId("eq-deployment-confirm").click();
  await expect(page.getByTestId("deployment-status")).toHaveAttribute(
    "data-status",
    "on_site",
  );
  await expect(page.getByTestId("not-usable")).toBeVisible();
  await page.getByTestId("arrival-inspection").click();
  for (let i = 1; i <= 8; i++)
    await page.getByTestId(`aic-AIC-0${i}-pass`).click();
  await page.getByTestId("arrival-confirm").click();
  await expect(page.getByTestId("not-usable")).toHaveCount(0);

  // EQ sticker (QR + printed ref) and the field check of that printed ref (AC71: no personal data).
  await page.getByTestId("print-eq-sticker").click();
  await expect(page.getByTestId("eq-sticker-print")).toBeVisible();
  await expect(page.getByTestId("eq-printed-ref")).toHaveText(
    `ANIA-EXP-${tag}`,
  );
  await page.goto("/en/cert-check");
  await certCheckReady(page);
  await page.getByTestId("cc-ref").fill(`ANIA-EXP-${tag}`);
  await page.getByTestId("cc-ref-check").click();
  await expect(page.getByTestId("cc-result")).toHaveAttribute(
    "data-result",
    "in_service",
  );
  const card = page.getByTestId("equipment-card");
  await expect(card).toContainText(certNo);
  await expect(card).toContainText("AICC");
  await expect(card).toContainText("3.000 t");
  await expect(card).not.toContainText("E2E Inspector");
});

test("AC71: a site engineer's check of RW-MC-03's EQ sticker shows the certificate, SWL and validity, and no personal data", async ({
  page,
}) => {
  // Fahad (site engineer, S-LAND). Omar's grant covers another site and gets OUT_OF_SCOPE (reported as a doubt on AC71).
  await login(page, USERS4.fahad);
  await page.goto("/en/cert-check");
  await certCheckReady(page);
  await page.getByTestId("cc-ref").fill("ANIA-EXP-RW-MC-03");
  await page.getByTestId("cc-ref-check").click();
  await expect(page.getByTestId("cc-result")).toHaveAttribute(
    "data-result",
    "in_service",
  );
  const card = page.getByTestId("equipment-card");
  await expect(card).toHaveAttribute("data-colour", "green");
  await expect(card).toContainText("RW-MC-03");
  await expect(card).toContainText("RAWABI");
  await expect(card).toContainText("AICC-EQ-TEST-25-1106");
  await expect(card).toContainText("50.000 t");
  await expect(card.getByTestId("eq-valid-until")).toContainText("5 Nov 2026");
  await expect(card).not.toContainText(/WKR-|iqama|inspector/i);
});
