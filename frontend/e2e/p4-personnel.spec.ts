import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, uid, USERS } from "./helpers";
import { accessCard, selectContaining } from "./p2-helpers";
import { certCheckReady } from "./p4-helpers";

interface Dep {
  id: string;
  worker_id: string;
}

async function deploymentOf(code: string, workerNo: string): Promise<Dep> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, code);
  const list = await getJson<{ items: Dep[] }>(
    api,
    `/api/v1/projects/${pid}/deployments?q=${workerNo}`,
  );
  const d = list.items[0];
  if (!d) throw new Error(`${workerNo} has no deployment on ${code}`);
  return d;
}

/** Personnel certificates against the Appendix A seed (spec 4 §3.9, §5.6, §5.9; AC53, AC62, AC72, AC82, AC107). */
test.describe("Personnel certificates", () => {
  test("AC53: the ID on the card is matched and never stored; a wrong ID is refused with nothing stored", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const certNo = `AICC-RG-TEST-26-${uid()}`;
    await login(page, USERS.ahmed);
    await page.goto("/en/personnel-certificates/new");
    await page.getByTestId("pc-holder-search").fill("Zaheer");
    await selectContaining(page.getByTestId("pc-holder"), "WKR-000019");
    await expect(page.getByTestId("holder-selected")).toContainText(
      "Zaheer Abbas",
    );
    await page.getByTestId("pc-id-number").fill("2000001091");
    await page.getByTestId("pc-cert-type").selectOption("RIGGER");
    await selectContaining(page.getByTestId("pc-tpi"), "AICC");
    await page.getByTestId("pc-cert-no").fill(certNo);
    await page.getByTestId("pc-issued").fill("2026-09-01");
    await page.getByTestId("pc-level").selectOption("2");
    await page.getByTestId("pc-name-as-printed").fill("Zaheer Abbas");
    await expect(page.getByTestId("preview-name-match")).toHaveAttribute(
      "data-match",
      "exact",
      { timeout: 20_000 },
    );
    await page.getByTestId("save-pcert").click();
    await expect(page.getByTestId("form-error")).toHaveAttribute(
      "data-code",
      "CERT_ID_MISMATCH",
    );

    // The right number: the match is recorded, the number itself is not shown or stored.
    await page.getByTestId("pc-id-number").fill("2000001019");
    await page.getByTestId("save-pcert").click();
    await expect(page).toHaveURL(/\/personnel-certificates\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("id-match")).toHaveAttribute(
      "data-result",
      "matched",
    );
    await expect(page.locator("main")).not.toContainText("2000001019");
  });

  test("AC82: a SCAFFOLDER card for banned Nadeem Akhtar is refused with no reason given to the contractor", async ({
    page,
  }) => {
    await login(page, USERS.ahmed);
    await page.goto("/en/personnel-certificates/new");
    await page.getByTestId("pc-holder-search").fill("Nadeem");
    await selectContaining(page.getByTestId("pc-holder"), "WKR-000022");
    await page.getByTestId("id-on-card").getByRole("checkbox").uncheck();
    await page.getByTestId("pc-cert-type").selectOption("SCAFFOLDER");
    await selectContaining(page.getByTestId("pc-tpi"), "DSPC");
    await page.getByTestId("pc-cert-no").fill(`DSPC-SC-TEST-26-${uid()}`);
    await page.getByTestId("pc-issued").fill("2026-09-01");
    await page.getByTestId("pc-level").selectOption("basic");
    await page.getByTestId("pc-name-as-printed").fill("Nadeem Akhtar");
    await expect(page.getByTestId("preview-issues")).toContainText(
      "Certification not accepted on this organisation's projects",
      { timeout: 20_000 },
    );
    await page.getByTestId("save-pcert").click();
    const err = page.getByTestId("form-error");
    await expect(err).toHaveAttribute("data-code", "HOLDER_BANNED");
    await expect(err).toContainText(
      "Certification not accepted on this organisation's projects",
    );
    // The contractor is told only that it is not accepted: no ban reason, no verification outcome.
    await expect(err).not.toContainText(
      /QUICKCERT|not found|verification|review/i,
    );
    await expect(page.getByTestId("preview-issues")).not.toContainText(
      /QUICKCERT|not found|verification|review/i,
    );
  });

  test("AC62/BL-4: worker pages show Bikash Rai's missing trade certificate and Nadeem Akhtar's certification ban", async ({
    page,
  }) => {
    const api = await apiAs(USERS.faisal);
    const rbt = await projectId(api, "RBT-52");
    const bikash = await deploymentOf("RBT-52", "WKR-000104");
    const nadeem = await deploymentOf("ANIA-EXP", "WKR-000022");
    await login(page, USERS.faisal);
    await page.goto(`/en/workers/${nadeem.worker_id}`);
    const panel = page.getByTestId("worker-certificates");
    await expect(panel.getByTestId("cert-ban")).toBeVisible();

    await page.getByTestId("project-switcher").selectOption(rbt);
    await page.goto(`/en/workers/${bikash.worker_id}`);
    await expect(page.getByTestId("trade-requirement")).toHaveAttribute(
      "data-met",
      "no",
    );
    await expect(
      page.locator('[data-testid=worker-cert][data-type="RIGGER"]'),
    ).toHaveAttribute("data-in-force", "no");
  });

  test("AC72: checking Joel Bautista's access card shows his in-force certificates and no ID, scan or medical data", async ({
    page,
  }) => {
    const api = await apiAs(USERS.faisal);
    const rbt = await projectId(api, "RBT-52");
    const joel = await deploymentOf("RBT-52", "WKR-000108");
    const card = await accessCard(api, joel.id);
    await login(page, USERS.faisal);
    await page.getByTestId("project-switcher").selectOption(rbt);
    await page.goto("/en/cert-check");
    await expect(page.getByTestId("cc-ref")).toBeVisible();
    await certCheckReady(page);
    await page.evaluate(
      (p) =>
        (
          window as unknown as { __hseCertScan: (x: string) => Promise<void> }
        ).__hseCertScan(p),
      card.qr_payload,
    );
    const person = page.getByTestId("person-cert-card");
    await expect(person).toBeVisible();
    await expect(person).toContainText("Joel Bautista");
    await expect(person).toContainText("WKR-000108");
    await expect(
      person.locator('[data-testid=person-cert][data-code="RIGGER"]'),
    ).toHaveAttribute("data-in-force", "1");
    await expect(
      person.locator('[data-testid=person-cert][data-code="SIGNALLER"]'),
    ).toHaveAttribute("data-in-force", "1");
    await expect(person).toContainText("20 Oct 2026");
    await expect(person).not.toContainText(/iqama|\d\*{4,}\d|medical/i);
  });

  test("AC107: the viewer cannot read personnel certificates", async () => {
    const sarah = await apiAs(USERS.sarah);
    const pid = await projectId(await apiAs(USERS.faisal), "ANIA-EXP");
    const res = await sarah.get(
      `/api/v1/projects/${pid}/personnel-certificates`,
    );
    expect(res.status()).toBe(403);
  });
});
