import { expect, test } from "./fixtures/test";
import { login, USERS } from "./helpers";
import { selectContaining } from "./p2-helpers";

/** Scaffold tag board and inspections against the Appendix A seed (spec 4 §3.8, §4.6, §5.5; AC42–AC45, AC114). */
test.describe("Scaffolds", () => {
  test("AC42/AC43/AC44: the tag board shows SC-0142 green to 7 Oct, SC-0150 red (not usable) and SC-0151 yellow with its restriction", async ({
    page,
  }) => {
    await login(page, USERS.noura);
    await page.goto("/en/scaffold-board");
    const board = page.getByTestId("scaffold-board");
    await expect(board).toBeVisible();
    const green = board.locator('[data-testid=board-tag][data-tag="SC-0142"]');
    await expect(green).toHaveAttribute("data-tag-status", "green");
    await expect(green).toContainText("7 Oct 2026");
    await expect(
      board.locator('[data-testid=board-tag][data-tag="SC-0150"]'),
    ).toHaveAttribute("data-tag-status", "red");
    await expect(
      board.locator('[data-testid=board-tag][data-tag="SC-0151"]'),
    ).toHaveAttribute("data-tag-status", "yellow");

    // AC43: the red scaffold is not usable today.
    await board.locator('[data-testid=board-tag][data-tag="SC-0150"]').click();
    await expect(page.getByTestId("scaffold-usable")).toHaveAttribute(
      "data-usable",
      "no",
    );

    // AC44: the yellow tag is usable with its restriction shown.
    await page.goto("/en/scaffold-board");
    await page.locator('[data-testid=board-tag][data-tag="SC-0151"]').click();
    await expect(page.getByTestId("scaffold-usable")).toHaveAttribute(
      "data-usable",
      "yes",
    );
    await expect(page.getByTestId("scaffold-restrictions")).toContainText(
      /harness and lanyard required/i,
    );
  });

  test("AC45: Imran Hussain (SCAFFOLDER only) cannot record an inspection; Ferdinand Reyes (SCAFFOLD-INSPECTOR) can", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await login(page, USERS.noura);
    await page.goto("/en/scaffold-board");
    await page.locator('[data-testid=board-tag][data-tag="SC-0142"]').click();
    await expect(page.getByTestId("scaffold-usable")).toBeVisible();

    const inspect = async (name: string) => {
      await page.getByTestId("inspect-scaffold").click();
      const dlg = page.getByRole("dialog");
      await dlg.getByTestId("si-inspector-search").fill(name);
      await selectContaining(dlg.getByTestId("si-inspector"), name);
      await dlg.getByTestId("sic-all-pass").click();
      await dlg.getByTestId("si-result-green").click();
      await dlg.getByTestId("inspection-confirm").click();
      return dlg;
    };

    const dlg = await inspect("Imran");
    await expect(dlg.getByTestId("form-error")).toHaveAttribute(
      "data-code",
      "INSPECTOR_NOT_CERTIFIED",
    );
    await page.keyboard.press("Escape");
    await expect(dlg).toBeHidden();

    const before = await page
      .getByTestId("scaffold-inspections")
      .locator("li")
      .count();
    const ok = await inspect("Ferdinand");
    await expect(ok).toBeHidden();
    await expect(
      page.getByTestId("scaffold-inspections").locator("li"),
    ).toHaveCount(before + 1);
    await expect(page.getByTestId("scaffold-usable")).toHaveAttribute(
      "data-usable",
      "yes",
    );
  });

  test("AC114: the tag board in Arabic on a phone is right-to-left, keeps tags left-to-right and does not scroll sideways", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, USERS.noura, "ar");
    await page.goto("/ar/scaffold-board");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const tag = page.locator('[data-testid=board-tag][data-tag="SC-0142"]');
    await expect(tag).toBeVisible();
    await expect(tag.locator(".ltr").first()).toHaveCSS("direction", "ltr");
    await expect(tag).toContainText("أخضر");
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
