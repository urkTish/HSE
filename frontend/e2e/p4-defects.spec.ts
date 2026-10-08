import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, USERS } from "./helpers";
import { certCheckReady, USERS4 } from "./p4-helpers";

async function defectId(no: string): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, "ANIA-EXP");
  const list = await getJson<{ items: { id: string; defect_no: string }[] }>(
    api,
    `/api/v1/projects/${pid}/defects?q=${no}&page_size=10`,
  );
  const d = list.items.find((x) => x.defect_no === no);
  if (!d) throw new Error(`${no} not found`);
  return d.id;
}

async function equipmentByTag(tag: string): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, "ANIA-EXP");
  const list = await getJson<{
    items: { id: string; current_tag: string | null }[];
  }>(api, `/api/v1/equipment?project_id=${pid}&q=${tag}&page_size=10`);
  const e = list.items.find((x) => x.current_tag === tag);
  if (!e) throw new Error(`${tag} not found`);
  return e.id;
}

/** Defects, out of service and return to service against the Appendix A seed (spec 4 §3.11, §4.5, §5.8; AC73, AC74, AC77, AC78, AC79). */
test.describe("Defects", () => {
  test("AC73: RW-MEWP-07 with an open A defect is Out of Service and its sticker check shows OUT OF SERVICE", async ({
    page,
  }) => {
    const id = await equipmentByTag("RW-MEWP-07");
    await login(page, USERS.noura);
    await page.goto(`/en/equipment/${id}`);
    await expect(page.getByTestId("service-status").first()).toHaveAttribute(
      "data-status",
      "out_of_service",
    );
    await expect(page.getByTestId("equipment-stop")).toBeVisible();
    await page.goto("/en/cert-check");
    await certCheckReady(page);
    await page.getByTestId("cc-ref").fill("ANIA-EXP-RW-MEWP-07");
    await page.getByTestId("cc-ref-check").click();
    await expect(page.getByTestId("cc-result")).toHaveAttribute(
      "data-result",
      "not_usable",
    );
    await expect(page.getByTestId("equipment-card")).toContainText(
      /out of service/i,
    );
  });

  test("AC74: B defect DEF-ANIA-EXP-2026-0005 is due 24 Oct 2026, a week before the TPI date", async ({
    page,
  }) => {
    const id = await defectId("DEF-ANIA-EXP-2026-0005");
    await login(page, USERS.noura);
    await page.goto(`/en/defects/${id}`);
    await expect(page.getByTestId("defect-status").first()).toHaveAttribute(
      "data-status",
      "open",
    );
    await expect(page.locator("main")).toContainText("24 Oct 2026");
    await expect(page.locator("main")).toContainText("31 Oct 2026");
  });

  test("AC77: the contractor rectifies RW-MEWP-07 but cannot return it to service; closing without a re-inspection line is refused", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const id = await defectId("DEF-ANIA-EXP-2026-0007");
    const eq = await equipmentByTag("RW-MEWP-07");
    await login(page, USERS.ahmed);
    await page.goto(`/en/defects/${id}`);
    await page.getByTestId("defect-rectify").click();
    await page.getByTestId("dr-by").fill("RAWABI hydraulics fitter (test)");
    await page
      .getByTestId("df-step-text")
      .fill("Slew ring seal replaced and leak-tested.");
    await page.getByTestId("defect-step-confirm").click();
    await expect(page.getByTestId("rectification")).toBeVisible();
    // The rectifying contractor has no return-to-service or close action (SoD, DF-6).
    await expect(page.getByTestId("defect-close")).toHaveCount(0);
    await page.goto(`/en/equipment/${eq}`);
    await expect(page.getByTestId("service-status").first()).toHaveAttribute(
      "data-status",
      "out_of_service",
    );
    await expect(page.getByTestId("return-to-service")).toHaveCount(0);

    // Noura cannot close it on the pre-repair certificate line.
    await page.context().clearCookies();
    await login(page, USERS.noura);
    await page.goto(`/en/defects/${id}`);
    await page.getByTestId("defect-close").click();
    const dlg = page.getByRole("dialog");
    await dlg.getByTestId("dc-method").selectOption("tpi_certificate");
    await dlg.getByTestId("dc-line").selectOption({ index: 1 });
    await dlg
      .getByTestId("df-step-text")
      .fill("Closing on the existing certificate (test).");
    await dlg.getByTestId("defect-step-confirm").click();
    await expect(dlg.getByTestId("form-error")).toHaveAttribute(
      "data-code",
      "TPI_REINSPECTION_REQUIRED",
    );
  });

  test("AC78: a site engineer tags out GP-EX-05 and it is Out of Service at once", async ({
    page,
  }) => {
    const id = await equipmentByTag("GP-EX-05");
    await login(page, USERS4.fahad);
    await page.goto(`/en/equipment/${id}`);
    await expect(page.getByTestId("service-status").first()).toHaveAttribute(
      "data-status",
      "in_service",
    );
    await page.getByTestId("tag-out").click();
    await page.getByTestId("eq-reason").fill("boom cylinder weeping");
    await page.getByTestId("equipment-confirm").click();
    await expect(page.getByTestId("service-status").first()).toHaveAttribute(
      "data-status",
      "out_of_service",
    );
    await expect(page.getByTestId("equipment-stop")).toContainText(
      "boom cylinder weeping",
    );
  });

  test("AC79: the lifting-gear incident prompts the investigator to link or raise a defect and shows the linked one", async ({
    page,
  }) => {
    const api = await apiAs(USERS.faisal);
    const pid = await projectId(api, "ANIA-EXP");
    const list = await getJson<{ items: { id: string; ref: string }[] }>(
      api,
      `/api/v1/projects/${pid}/incidents?q=0150&page_size=10`,
    );
    const inc = list.items.find((x) => x.ref === "INC-ANIA-EXP-2026-0150");
    expect(inc).toBeTruthy();
    await login(page, USERS.noura);
    await page.goto(`/en/incidents/${inc?.id}`);
    const prompt = page.getByTestId("incident-defect-prompt");
    await expect(prompt).toBeVisible();
    await expect(prompt).toContainText("DEF-ANIA-EXP-2026-0004");
    await expect(
      prompt.getByTestId("raise-defect-from-incident"),
    ).toBeVisible();
  });
});
