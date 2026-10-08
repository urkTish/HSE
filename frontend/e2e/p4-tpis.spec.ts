import { expect, test } from "./fixtures/test";
import { login, uid, USERS } from "./helpers";
import { pickMulti } from "./p2-helpers";
import { PDF, uploadInto } from "./p4-helpers";

/** TPI organisations (spec 4 §3.1–§3.2, §4.1; AC2, AC4, AC5). */
test.describe("TPI organisations", () => {
  test("AC2/AC4/AC5: create, accredit, register-check and approve a TPI; no training-provider kind; Noura cannot approve", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const code = `T${uid()}`;
    await login(page, USERS.faisal);
    await page.goto("/en/tpis");
    await page.getByTestId("new-tpi").click();
    // AC2: exactly the five TPI kinds, none for training providers (BD-3).
    const kinds = page.getByTestId("tpi-kinds").locator("input[type=checkbox]");
    await expect(kinds).toHaveCount(5);
    await expect(
      page.getByTestId("tpi-kinds").locator("label"),
    ).not.toContainText([/training provider/i]);
    await page.getByTestId("tpi-code").fill(code);
    await page
      .getByTestId("tpi-name-en")
      .fill(`E2E Lifting Inspection ${code}`);
    await page.getByTestId("tpi-name-ar").fill(`فحص الرفع ${code}`);
    await page
      .getByTestId("tpi-kinds")
      .getByText("Inspection body", { exact: false })
      .first()
      .click();
    await page
      .getByTestId("tpi-cr")
      .fill("1010" + String(Date.now()).slice(-6));
    await page
      .getByTestId("tpi-domains")
      .fill(`verify.${code.toLowerCase()}-test.example`);
    await page.getByTestId("save-tpi").click();
    await expect(page).toHaveURL(/\/tpis\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("tpi-status").first()).toHaveAttribute(
      "data-status",
      "draft",
    );

    // Accreditation with the certificate PDF; it does not count until the register is checked (AC5).
    await page.getByTestId("new-accreditation").click();
    await page.getByTestId("acc-standard").selectOption("iso_iec_17020");
    await page.getByTestId("acc-no").fill(`IB-${code}`);
    await page.getByTestId("acc-from").fill("2026-01-01");
    await page.getByTestId("acc-until").fill("2027-12-31");
    await pickMulti(page, "acc-cats", ["Mobile crane"]);
    await uploadInto(page, "acc-file", PDF());
    await page.getByTestId("save-accreditation").click();
    const row = page.getByTestId("accreditation-row").first();
    await expect(row).toHaveAttribute("data-counts", "no");
    await expect(row.getByTestId("register-not-checked")).toBeVisible();
    await row.getByTestId("register-check").click();
    await expect(row).toHaveAttribute("data-counts", "yes");

    await page.getByTestId("tpi-submit").click();
    await page.getByTestId("tpi-confirm").click();
    await expect(page.getByTestId("tpi-status").first()).toHaveAttribute(
      "data-status",
      "pending_approval",
    );
    const url = page.url();

    // AC4: an HSE Officer has no approve action.
    await page.context().clearCookies();
    await login(page, USERS.noura);
    await page.goto(url.replace(/^https?:\/\/[^/]+/, ""));
    await expect(page.getByTestId("tpi-status").first()).toHaveAttribute(
      "data-status",
      "pending_approval",
    );
    await expect(page.getByTestId("tpi-approve")).toHaveCount(0);

    await page.context().clearCookies();
    await login(page, USERS.faisal);
    await page.goto(url.replace(/^https?:\/\/[^/]+/, ""));
    await page.getByTestId("tpi-approve").click();
    await page.getByTestId("tpi-confirm").click();
    await expect(page.getByTestId("tpi-status").first()).toHaveAttribute(
      "data-status",
      "approved",
    );
    await expect(page.getByTestId("history-panel")).toBeVisible();
  });
});
