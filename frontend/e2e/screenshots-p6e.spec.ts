import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { pinProject, USERS6 } from "./p6a-helpers";

// Phase 6e demo screenshots for docs/screenshots/phase-6e (run with SCREENSHOTS=1 on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-6e");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(1_800_000);

async function shot(page: Page, name: string, fullPage = false) {
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => undefined);
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

type Items<T> = { items: T[] };

for (const locale of ["en", "ar"] as const) {
  test(`phase 6e screens (${locale})`, async ({ page }) => {
    mkdirSync(OUT, { recursive: true });
    const noura = await apiAs(USERS.noura);
    const pid = await projectId(noura, "ANIA-EXP");
    const first = async <T extends { id: string }>(path: string, pick?: (x: T) => boolean) => {
      const r = await getJson<Items<T>>(noura, path);
      return (pick ? r.items.find(pick) : undefined) ?? r.items[0];
    };
    const aspect = await first<{ id: string; significant: boolean }>(`/api/v1/projects/${pid}/env-aspects?page_size=50`, (a) => a.significant);
    const permit = await first<{ id: string; status: string }>(`/api/v1/projects/${pid}/env-permits?page_size=50`, (p) => p.status === "expiring");
    const provider = await first<{ id: string; provider_code: string }>("/api/v1/env-providers?page_size=50", (p) => p.provider_code === "HAZMOVE");
    const area = await first<{ id: string; area_code: string }>(`/api/v1/projects/${pid}/waste-storage-areas?page_size=50`, (a) => a.area_code === "HWS-SLAND-01");
    const cons = await first<{ id: string; status: string }>(`/api/v1/projects/${pid}/waste-consignments?page_size=50`, (c) => c.status === "closed");
    const point = await first<{ id: string; point_code: string }>(`/api/v1/projects/${pid}/env-points?page_size=50`, (p) => p.point_code === "D-SAIR-01");
    const exc = await first<{ id: string; exceedance_no: string }>(`/api/v1/projects/${pid}/env-exceedances?page_size=50`, (x) => x.exceedance_no === "ENX-ANIA-EXP-2026-0017");
    const spill = await first<{ id: string; reportable: boolean }>(`/api/v1/projects/${pid}/spills?page_size=50`, (s) => s.reportable);
    const go = (path: string) => page.goto(`/${locale}${path}`);

    await login(page, USERS.noura, locale);
    await pinProject(page, "ANIA-EXP");

    await go("/env-overview");
    await expect(page.getByTestId("env-band")).toBeVisible();
    await shot(page, `01-env-overview-${locale}.png`, true);

    await go("/env-kpis?period=month&anchor=2026-09-15");
    await expect(page.getByTestId("ek-tiles")).toBeVisible({ timeout: 45_000 });
    await shot(page, `02-env-kpis-${locale}.png`, true);

    await go("/env-settings");
    await expect(page.getByTestId("env-settings")).toBeVisible();
    await shot(page, `03-env-settings-${locale}.png`, true);

    await go("/env-aspects");
    await expect(page.getByTestId("aspect-row").first()).toBeVisible();
    await shot(page, `04-aspects-${locale}.png`, true);
    if (aspect) {
      await go(`/env-aspects/${aspect.id}`);
      await expect(page.getByTestId("aspect-controls")).toBeVisible();
      await shot(page, `05-aspect-detail-${locale}.png`, true);
    }

    await go("/env-permits");
    await expect(page.getByTestId("permit-row").first()).toBeVisible();
    await shot(page, `06-permits-${locale}.png`, true);
    if (permit) {
      await go(`/env-permits/${permit.id}`);
      await expect(page.getByTestId("permit-status")).toBeVisible();
      await shot(page, `07-permit-detail-${locale}.png`, true);
    }

    await go("/env-providers");
    await expect(page.getByTestId("provider-row").first()).toBeVisible();
    await shot(page, `08-providers-${locale}.png`, true);
    if (provider) {
      await go(`/env-providers/${provider.id}`);
      await expect(page.getByTestId("licence-row").first()).toBeVisible();
      await shot(page, `09-provider-detail-${locale}.png`, true);
    }

    await go("/waste-streams");
    await expect(page.getByTestId("stream-row").first()).toBeVisible();
    await shot(page, `10-waste-streams-${locale}.png`, true);

    await go("/waste-areas");
    await expect(page.getByTestId("area-card").first()).toBeVisible();
    await shot(page, `11-waste-areas-${locale}.png`, true);

    await go("/waste-consignments");
    await expect(page.getByTestId("consignment-row").first()).toBeVisible();
    await shot(page, `12-consignments-${locale}.png`, true);
    if (cons) {
      await go(`/waste-consignments/${cons.id}`);
      await expect(page.getByTestId("received-net")).toBeVisible();
      await shot(page, `13-consignment-detail-${locale}.png`, true);
    }
    await go(`/waste-consignments/new?area=${area?.id ?? ""}`);
    await expect(page.getByTestId("cn-stream")).toBeVisible();
    await shot(page, `14-dispatch-${locale}.png`, true);

    await go("/env-points");
    await expect(page.getByTestId("point-row").first()).toBeVisible();
    await shot(page, `15-points-${locale}.png`, true);
    if (point) {
      await go(`/env-points/${point.id}`);
      await expect(page.getByTestId("requirement-row").first()).toBeVisible();
      await shot(page, `16-point-detail-${locale}.png`, true);
    }

    await go("/env-readings");
    await expect(page.getByTestId("reading-row").first()).toBeVisible();
    await shot(page, `17-readings-${locale}.png`, true);

    await go("/env-exceedances");
    await expect(page.getByTestId("exceedance-row").first()).toBeVisible();
    await shot(page, `18-exceedances-${locale}.png`, true);
    if (exc) {
      await go(`/env-exceedances/${exc.id}`);
      await expect(page.getByTestId("exceedance-peak")).toBeVisible();
      await shot(page, `19-exceedance-detail-${locale}.png`, true);
    }

    await go("/env-water");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await shot(page, `20-water-${locale}.png`, true);

    await go("/spills");
    await expect(page.getByTestId("spill-row").first()).toBeVisible();
    await shot(page, `21-spills-${locale}.png`, true);
    if (spill) {
      await go(`/spills/${spill.id}`);
      await expect(page.getByTestId("env-status").first()).toBeVisible();
      await shot(page, `22-spill-detail-${locale}.png`, true);
    }
    await go("/spills/new");
    await expect(page.getByTestId("sp-site")).toBeVisible();
    await shot(page, `23-spill-new-${locale}.png`, true);

    await go("/env-complaints/new");
    await expect(page.getByTestId("cp-privacy")).toBeVisible();
    await shot(page, `24-complaint-new-${locale}.png`, true);

    // A complaint so the register and the detail have content (ANIA-EXP has none seeded).
    await page.getByTestId("cp-channel").selectOption("phone");
    await page.getByTestId("cp-category").selectOption({ index: 1 });
    await page.getByTestId("cp-site").selectOption({ index: 1 });
    await page.getByTestId("cp-name").fill(locale === "en" ? "Resident, block 4" : "ساكن، المبنى 4");
    await page.getByTestId("cp-contact").fill("+966 55 000 1234");
    await page.getByTestId("cp-description").fill(locale === "en" ? "Dust reaches the houses on the north fence every afternoon." : "يصل الغبار إلى المنازل عند السور الشمالي كل عصر.");
    await page.getByTestId("cp-save").click();
    await expect(page.getByTestId("complainant-contact")).toBeVisible();
    await shot(page, `25-complaint-detail-${locale}.png`, true);
    await go("/env-complaints");
    await expect(page.getByTestId("complaint-row").first()).toBeVisible();
    await shot(page, `26-complaints-${locale}.png`, true);

    // Phone: the reading entry and the waste-area check at 390 px.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.context().clearCookies();
    await login(page, USERS.omar, locale);
    await pinProject(page, "ANIA-EXP");
    await go("/env-readings/new");
    await page.getByTestId("rd-point-V-SAIR").click();
    await page.getByTestId("rd-visual-2").click();
    await shot(page, `27-phone-reading-${locale}.png`, true);

    await page.context().clearCookies();
    await login(page, USERS6.fahad, locale);
    await pinProject(page, "ANIA-EXP");
    await go(`/waste-areas/${area?.id ?? ""}`);
    await expect(page.getByTestId("area-check")).toBeVisible();
    await shot(page, `28-phone-area-check-${locale}.png`, true);
  });
}
