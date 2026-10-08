import { execFileSync } from "node:child_process";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, uid, USERS } from "./helpers";
import { makePdf } from "./p4-helpers";

interface Item {
  serial_no: string;
  current_tag: string | null;
}

/** A zip of one PDF scan per cert_no (named <cert_no>.pdf), built with Python's zipfile. */
function scansZip(certNos: string[]): Buffer {
  const pdf = makePdf().toString("base64");
  const script = [
    "import base64, io, sys, zipfile",
    "pdf = base64.b64decode(sys.argv[1])",
    "buf = io.BytesIO()",
    "z = zipfile.ZipFile(buf, 'w')",
    "for n in sys.argv[2:]: z.writestr(n + '.pdf', pdf)",
    "z.close()",
    "sys.stdout.write(base64.b64encode(buf.getvalue()).decode())",
  ].join("\n");
  return Buffer.from(
    execFileSync("python3", ["-c", script, pdf, ...certNos], {
      encoding: "utf8",
    }),
    "base64",
  );
}

const HEAD =
  "project_code,tag,equipment_no,category,manufacturer,serial_no,tpi_code,cert_no,inspection_type,inspected_on,issued_on,printed_next_due,result,swl_t,load_test_pct,limitations,defects,colour_code,inspector_name,model,contractor_code";

/**
 * Certificate imports (spec 4 §3.15, §4.9, §5.11; AC98, AC99, AC101, AC102). A 10-row NAJD accessory file:
 * 2 unknown TPI codes (E04), 1 serial mismatch (E05), 2 printed dates beyond the interval (W01), 7 valid rows.
 */
test.describe.serial("Certificate imports", () => {
  const sfx = uid();
  let csv = "";
  let zip: Buffer = Buffer.alloc(0);
  const certNos: string[] = [];

  test.beforeAll(async () => {
    const api = await apiAs(USERS.faisal);
    const pid = await projectId(api, "ANIA-EXP");
    const list = await getJson<{ items: Item[] }>(
      api,
      `/api/v1/equipment?project_id=${pid}&q=NJ-ACC&page_size=50`,
    );
    const items = list.items
      .filter((x) => x.current_tag)
      .sort((a, b) => (a.current_tag ?? "").localeCompare(b.current_tag ?? ""))
      .slice(0, 10);
    expect(items).toHaveLength(10);
    const rows = items.map((x, i) => {
      const certNo = `AICC-EQ-TEST-26-I${sfx}${String(i).padStart(2, "0")}`;
      certNos.push(certNo);
      const tpi = i < 2 ? "NOSUCHTPI" : "AICC";
      const serial = i === 2 ? `${x.serial_no}-X` : x.serial_no;
      const printed = i === 3 || i === 4 ? "2027-09-30" : "";
      return `ANIA-EXP,${x.current_tag},,lifting_accessory,TestLift,${serial},${tpi},${certNo},periodic,2026-10-01,2026-10-02,${printed},pass,5.000,,,,,E2E Inspector (fake),,`;
    });
    csv = `${HEAD}\r\n${rows.join("\r\n")}\r\n`;
    zip = scansZip(certNos);
  });

  async function upload(page: import("@playwright/test").Page) {
    await page.goto("/en/certificate-imports");
    await page
      .getByTestId("ci-template")
      .selectOption("equipment_certificates");
    await page.getByTestId("ci-source").selectOption("contractor_file");
    await page
      .getByTestId("ci-file")
      .setInputFiles({
        name: `najd-accessories-${sfx}.csv`,
        mimeType: "text/csv",
        buffer: Buffer.from(csv, "utf8"),
      });
    await page
      .getByTestId("ci-scans")
      .setInputFiles({
        name: "scans.zip",
        mimeType: "application/zip",
        buffer: zip,
      });
    await page.getByTestId("ci-check").click();
    await expect(page).toHaveURL(/\/certificate-imports\/[0-9a-f-]{36}$/, {
      timeout: 30_000,
    });
  }

  test("AC98/AC99: the dry-run reports E04 × 2, E05 × 1 and W01 × 2; commit creates Submitted certificates for the 7 valid rows", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await login(page, USERS.noura);
    await upload(page);
    await expect(page.getByTestId("ci-row")).toHaveCount(5); // errors and warnings only
    await page.getByRole("checkbox", { name: "Show OK rows" }).check();
    await expect(page.getByTestId("ci-row")).toHaveCount(10);
    await expect(
      page.locator("[data-testid=ci-row][data-status=error]"),
    ).toHaveCount(3);
    await expect(page.getByTestId("ci-rows")).toContainText("E04");
    await expect(page.getByTestId("ci-rows")).toContainText("E05");
    await expect(page.getByTestId("ci-rows")).toContainText("W01");
    const commit = page.getByTestId("ci-commit");
    await expect(commit).toContainText("7");
    await commit.click();
    const confirm = page.getByRole("dialog");
    if (await confirm.isVisible().catch(() => false))
      await confirm.getByRole("button").last().click();
    await expect(page.getByTestId("ci-committed")).toBeVisible({
      timeout: 30_000,
    });

    // AC99: committed rows are Submitted, never Accepted.
    const api = await apiAs(USERS.faisal);
    const pid = await projectId(api, "ANIA-EXP");
    const certs = await getJson<{
      items: { cert_no: string; status: string }[];
    }>(
      api,
      `/api/v1/projects/${pid}/equipment-certificates?q=I${sfx}&page_size=50`,
    );
    expect(certs.items.length).toBe(7);
    for (const c of certs.items) expect(c.status).toBe("submitted");
  });

  test("AC102: uploading the same file again warns W05", async ({ page }) => {
    await login(page, USERS.noura);
    await upload(page);
    await expect(page.locator("main")).toContainText("W05");
    await page.getByTestId("ci-discard").click();
    const confirm = page.getByRole("dialog");
    if (await confirm.isVisible().catch(() => false))
      await confirm.getByRole("button").last().click();
  });

  test("AC101: a contractor HSE Rep is not offered the TPI register source", async ({
    page,
  }) => {
    await login(page, USERS.ahmed);
    await page.goto("/en/certificate-imports");
    await expect(
      page.getByTestId("ci-source").locator("option[value=tpi_register_file]"),
    ).toHaveCount(0);
    await expect(
      page.getByTestId("ci-source").locator("option[value=contractor_file]"),
    ).toHaveCount(1);
  });
});
