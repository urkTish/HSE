import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./fixtures/test";
import { apiAs, getJson, login, projectId, uid, USERS } from "./helpers";
import { makePdf } from "./p4-helpers";

// Phase 4 demo screenshots for docs/screenshots/phase-4 (run with SCREENSHOTS=1, ideally on a fresh seed).
const OUT = join(__dirname, "..", "..", "docs", "screenshots", "phase-4");
test.skip(!process.env.SCREENSHOTS, "screenshots only on demand");
test.setTimeout(300_000);

async function find(path: string, key: string, value: string, project = "ANIA-EXP"): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, project);
  const url = path.startsWith("/") ? `${path}${path.includes("?") ? "&" : "?"}project_id=${pid}&q=${encodeURIComponent(value)}&page_size=50` : `/api/v1/projects/${pid}/${path}?q=${encodeURIComponent(value)}&page_size=50`;
  const list = await getJson<{ items: Record<string, string>[] }>(api, url);
  return list.items.find((x) => x[key] === value)?.id ?? "";
}

async function shot(page: Page, name: string, fullPage = false) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, name), fullPage });
}

async function gateToken(gateCode: string): Promise<string> {
  const api = await apiAs(USERS.faisal);
  const pid = await projectId(api, "ANIA-EXP");
  const gates = await getJson<{ items: { id: string; gate_code: string }[] }>(api, `/api/v1/projects/${pid}/gates`);
  const g = gates.items.find((x) => x.gate_code === gateCode);
  const res = await api.post(`/api/v1/gates/${g?.id}/devices`, { data: { device_id: `TAB-SHOT-${uid()}`, label: "Demo tablet" } });
  return ((await res.json()) as { device_token: string }).device_token;
}

function importFile(items: { serial_no: string; current_tag: string | null }[], sfx: string): { csv: string; zip: Buffer } {
  const head =
    "project_code,tag,equipment_no,category,manufacturer,serial_no,tpi_code,cert_no,inspection_type,inspected_on,issued_on,printed_next_due,result,swl_t,load_test_pct,limitations,defects,colour_code,inspector_name,model,contractor_code";
  const certNos: string[] = [];
  const rows = items.map((x, i) => {
    const certNo = `AICC-EQ-TEST-26-D${sfx}${String(i).padStart(2, "0")}`;
    certNos.push(certNo);
    const tpi = i === 0 ? "NOSUCHTPI" : "AICC";
    const serial = i === 1 ? `${x.serial_no}-X` : x.serial_no;
    const printed = i === 2 ? "2027-09-30" : "";
    return `ANIA-EXP,${x.current_tag},,lifting_accessory,TestLift,${serial},${tpi},${certNo},periodic,2026-10-01,2026-10-02,${printed},pass,5.000,,,,,Demo Inspector (fake),,`;
  });
  const script = [
    "import base64, io, sys, zipfile",
    "pdf = base64.b64decode(sys.argv[1])",
    "buf = io.BytesIO()",
    "z = zipfile.ZipFile(buf, 'w')",
    "for n in sys.argv[2:]: z.writestr(n + '.pdf', pdf)",
    "z.close()",
    "sys.stdout.write(base64.b64encode(buf.getvalue()).decode())",
  ].join("\n");
  const zip = Buffer.from(execFileSync("python3", ["-c", script, makePdf().toString("base64"), ...certNos], { encoding: "utf8" }), "base64");
  return { csv: `${head}\r\n${rows.join("\r\n")}\r\n`, zip };
}

test("phase-4 demo screenshots", async ({ page, browser }) => {
  mkdirSync(OUT, { recursive: true });
  const mc03 = await find("/api/v1/equipment", "current_tag", "RW-MC-03");
  const zaheer = await find("personnel-certificates", "cert_no", "AICC-OP-TEST-24-0412");
  const def07 = await find("defects", "defect_no", "DEF-ANIA-EXP-2026-0007");
  const api = await apiAs(USERS.faisal);
  const ania = await projectId(api, "ANIA-EXP");
  const acc = await getJson<{ items: { serial_no: string; current_tag: string | null }[] }>(api, `/api/v1/equipment?project_id=${ania}&q=NJ-ACC&page_size=50`);

  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, USERS.faisal);

  // 1. Equipment detail with its in-force certificate.
  await page.goto(`/en/equipment/${mc03}`);
  await expect(page.getByTestId("current-line")).toBeVisible();
  await shot(page, "equipment-detail-certificate.png");

  // 2. Personnel certificate (scope, cap, verification).
  await page.goto(`/en/personnel-certificates/${zaheer}`);
  await expect(page.getByTestId("id-match")).toBeVisible();
  await shot(page, "personnel-certificate.png");

  // 3. Defect tag-out: an A defect holding the MEWP out of service.
  await page.goto(`/en/defects/${def07}`);
  await expect(page.getByTestId("defect-a-stop")).toBeVisible();
  await shot(page, "defect-tag-out.png");

  // 4. Hook policy: transition dates, codes and readiness.
  await page.goto("/en/hook-policy");
  await expect(page.getByTestId("hook-kind-personnel_certificate")).toBeVisible();
  await shot(page, "hook-policy.png");

  // 5. Import dry-run report.
  const f = importFile(acc.items.filter((x) => x.current_tag).slice(0, 6), uid());
  await page.goto("/en/certificate-imports");
  await page.getByTestId("ci-file").setInputFiles({ name: "najd-accessories-oct.csv", mimeType: "text/csv", buffer: Buffer.from(f.csv, "utf8") });
  await page.getByTestId("ci-scans").setInputFiles({ name: "scans.zip", mimeType: "application/zip", buffer: f.zip });
  await page.getByTestId("ci-check").click();
  await expect(page.getByTestId("ci-rows")).toBeVisible({ timeout: 30_000 });
  await shot(page, "import-dry-run.png");
  await page.getByTestId("ci-discard").click();

  // 6. Dashboard certification band (September 2026).
  await page.goto("/en?period=month&anchor=2026-09-15");
  const band = page.getByTestId("cert-band");
  await expect(band).toBeVisible();
  await band.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await band.screenshot({ path: join(OUT, "dashboard-cert-band.png") });

  // 7. Scaffold tag board on a phone, in Arabic.
  const ar = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "ar-SA", timezoneId: "Asia/Riyadh" });
  const m = await ar.newPage();
  await login(m, USERS.noura, "ar");
  await m.goto("/ar/scaffold-board");
  await expect(m.getByTestId("scaffold-board")).toBeVisible();
  await shot(m, "scaffold-board-mobile-ar.png");
  await ar.close();

  // 8. Gate: equipment DENIED (out of service) on the guard's phone.
  const g = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "en-GB", timezoneId: "Asia/Riyadh" });
  const gp = await g.newPage();
  const token = await gateToken("G-ANIA-01");
  await gp.goto("/en/gate");
  await gp.getByTestId("device-token-input").fill(token);
  await gp.getByTestId("device-login").click();
  await expect(gp.getByTestId("gate-ready")).toBeVisible();
  await gp.getByTestId("manual-ref").fill("ANIA-EXP-RW-MEWP-07");
  await gp.getByTestId("manual-check").click();
  await expect(gp.getByTestId("gate-result")).toHaveAttribute("data-result", "DENIED");
  await shot(gp, "gate-equipment-denied.png");
  await g.close();
});
