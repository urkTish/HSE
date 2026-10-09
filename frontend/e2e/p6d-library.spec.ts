import { expect, test } from "./fixtures/test";
import { uid, USERS } from "./helpers";
import { openAs } from "./p6a-helpers";

const letters = (s: string) => s.replace(/[0-9]/g, (d) => "ABCDEFGHIJ"[Number(d)] ?? "A");

/** Checklist template and toolbox topic libraries (6d §3.1, §3.6, TPL-1…TPL-6, TOP-1…TOP-4). */
test.describe("Field libraries", () => {
  test("Faisal drafts a template with a critical stop-work item and publishes it", async ({ page }) => {
    const code = `Q${letters(uid())}`.slice(0, 8);
    await openAs(page, USERS.faisal, "/checklist-templates");
    await page.getByTestId("tpl-new").click();
    await page.getByTestId("nt-code").fill(code);
    await page.getByTestId("nt-type").selectOption({ index: 1 });
    await page.getByTestId("nt-en").fill(`E2E checklist ${code}`);
    await page.locator("#nt-ar").fill(`قائمة تحقق ${code}`);
    await page.getByTestId("tpl-create").click();
    await expect(page.getByTestId("tpl-detail")).toHaveAttribute("data-status", "draft");

    await page.getByTestId("tpl-add-item").click();
    await expect(page.getByTestId("ti-code")).toHaveValue(`${code}-01`);
    await page.getByTestId("ti-en").fill("Edge protection in place at every open edge");
    await page.getByTestId("ti-ar").fill("حماية الحواف موجودة عند كل حافة مفتوحة");
    await page.getByTestId("ti-critical").check();
    await page.getByTestId("ti-stop").selectOption("stop_work");
    await page.getByTestId("item-save").click();
    const item = page.locator(`[data-testid="tpl-item"][data-code="${code}-01"]`);
    await expect(item).toBeVisible();

    await page.getByTestId("tpl-publish").click();
    await page.getByTestId("tpl-publish-confirm").click();
    await expect(page.getByTestId("tpl-detail")).toHaveAttribute("data-status", "published");
    await expect(page.getByTestId("tpl-edit")).toHaveCount(0);
    await expect(page.getByTestId("tpl-add-item")).toHaveCount(0);
    await expect(page.getByTestId("tpl-new-version")).toBeVisible();

    await page.goto("/en/checklist-templates");
    await expect(page.locator(`[data-testid="tpl-row"][data-code="${code}"]`)).toHaveAttribute("data-status", "published");
  });

  test("the officer authors but cannot publish; the client viewer only reads", async ({ page }) => {
    await openAs(page, USERS.noura, "/checklist-templates");
    await expect(page.getByTestId("tpl-new")).toBeVisible();
    await page.locator('[data-testid="tpl-row"][data-code="GSI"] a').first().click();
    await expect(page.getByTestId("tpl-detail")).toHaveAttribute("data-status", "published");
    await expect(page.getByTestId("tpl-retire")).toHaveCount(0);
    await expect(page.getByTestId("tpl-versions")).toBeVisible();

    await openAs(page, USERS.sarah, "/toolbox-topics");
    await expect(page.getByTestId("topic-row").first()).toBeVisible();
    await expect(page.getByTestId("topic-new")).toHaveCount(0);
  });

  test("Faisal writes a bilingual topic with key points and publishes it", async ({ page }) => {
    const code = `TT-9${String(Date.now() % 100).padStart(2, "0")}`;
    await openAs(page, USERS.faisal, "/toolbox-topics");
    await page.getByTestId("topic-new").click();
    await page.getByTestId("tt-code").fill(code);
    await page.getByTestId("tt-en").fill("Hand protection with power tools");
    await page.getByTestId("tt-ar").fill("حماية اليدين مع الأدوات الكهربائية");
    await page.getByTestId("tt-kpen").fill("Wear cut-resistant gloves\nCheck the guard before use\nUnplug before changing blades");
    await page.getByTestId("tt-kpar").fill("ارتدِ قفازات مقاومة للقطع\nافحص الواقي قبل الاستخدام\nافصل الكهرباء قبل تغيير الشفرات");
    await page.getByTestId("topic-save").click();
    await expect(page.getByTestId("topic-detail")).toHaveAttribute("data-status", "draft");
    await page.getByTestId("topic-publish").click();
    await page.getByTestId("topic-publish-confirm").click();
    await expect(page.getByTestId("topic-detail")).toHaveAttribute("data-status", "published");
    await expect(page.getByTestId("kp-ar").locator("li")).toHaveCount(3);
  });
});
