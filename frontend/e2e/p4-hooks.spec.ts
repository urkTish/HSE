import { expect, test } from "./fixtures/test";
import { apiAs, login, projectId, USERS } from "./helpers";

/** Hook policy and the warn → block transition (spec 4 §3.14, §4.8, §5.10; AC85, AC88, AC89, AC93). */
test.describe("Hook policy", () => {
  test("AC85/AC93: ANIA-EXP is in transition with critical codes blocking from 8 Oct and the rest from 31 Oct; readiness lists codes", async ({
    page,
  }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/hook-policy");
    for (const kind of ["personnel_certificate", "equipment_certificate"]) {
      const card = page.getByTestId(`hook-kind-${kind}`);
      await expect(card).toHaveAttribute("data-stage", "transition");
      await expect(card.getByTestId(`critical-from-${kind}`)).toContainText(
        "8 Oct 2026",
      );
      await expect(card.getByTestId(`general-from-${kind}`)).toContainText(
        "31 Oct 2026",
      );
    }
    // Severity legend: hard stops block in every stage; other not-met results only warn in transition.
    await expect(page.getByTestId("hard-stop").first()).toBeVisible();
    await expect(page.getByTestId("transition-warning").first()).toBeVisible();

    const ready = page.getByTestId("hook-readiness");
    await ready.getByTestId("rd-kind").selectOption("personnel_certificate");
    await expect(ready.getByTestId("readiness-RIGGER")).toBeVisible({
      timeout: 20_000,
    });
    await expect(ready.getByTestId("readiness-SCAFFOLDER")).toBeVisible();
  });

  test("AC88: the general block date can be deferred once, to 30 Nov 2026 at the latest", async ({
    page,
  }) => {
    await login(page, USERS.faisal);
    await page.goto("/en/hook-policy");
    const kind = "equipment_certificate";
    await page.getByTestId(`defer-${kind}`).click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.getByTestId("defer-date")).toHaveAttribute(
      "max",
      "2026-11-30",
    );
    await dlg.getByTestId("defer-date").fill("2026-11-30");
    await dlg
      .getByTestId("defer-reason")
      .fill("Contractor certification backlog after the Eid break (test).");
    await dlg.getByTestId("defer-confirm").click();
    await expect(dlg).toBeHidden();
    await expect(page.getByTestId(`deferral-${kind}`)).toBeVisible();
    await expect(page.getByTestId(`general-from-${kind}`)).toContainText(
      "30 Nov 2026",
    );
    // A second deferral is not offered (DEFERRAL_USED on the API).
    await expect(page.getByTestId(`defer-${kind}`)).toHaveCount(0);
    const api = await apiAs(USERS.faisal);
    const pid = await projectId(api, "ANIA-EXP");
    const again = await api.post(
      `/api/v1/projects/${pid}/hook-policy/${kind}/deferral`,
      {
        data: {
          new_date: "2026-11-29",
          reason: "A second deferral that must be refused (test).",
        },
      },
    );
    expect(again.status()).toBe(422);
    expect(
      ((await again.json()) as { detail: { code: string } }).detail.code,
    ).toBe("DEFERRAL_USED");
  });

  test("AC89: switching every personnel code on RBT-52 to block takes effect at once", async ({
    page,
  }) => {
    const api = await apiAs(USERS.faisal);
    const rbt = await projectId(api, "RBT-52");
    await login(page, USERS.faisal);
    await page.getByTestId("project-switcher").selectOption(rbt);
    await page.goto("/en/hook-policy");
    const kind = "personnel_certificate";
    const card = page.getByTestId(`hook-kind-${kind}`);
    await expect(card).toHaveAttribute("data-stage", "transition");
    await card.getByTestId(`switch-${kind}`).click();
    const dlg = page.getByRole("dialog");
    await dlg.locator("#sw-all").check();
    await dlg.getByTestId("switch-confirm").click();
    await expect(dlg).toBeHidden();
    await expect(card).toHaveAttribute("data-stage", "block");
    await expect(card.getByTestId("hook-code-RIGGER")).toHaveAttribute(
      "data-policy",
      "block",
    );
    await expect(card.getByTestId("hook-code-SCAFFOLDER")).toHaveAttribute(
      "data-policy",
      "block",
    );
  });
});
