"use client";
import { AlertTriangle, CheckCircle2, Plus, Star } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiWarnings } from "@/components/common/api-warnings";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { DecimalInput } from "@/components/ptw/common";
import { DateFilter } from "@/components/training/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useHeatRefresh, useHeatReference, useRestStations, useWelfareChecks } from "@/lib/api/heat";
import { zonedInputToUtc } from "@/lib/datetime";
import { WELFARE_ITEMS } from "@/lib/heat-enums";
import { StackedDate } from "@/components/medical/common";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { ChoiceMark, HeatFieldSubNav, HeatReasonDialog, RecordStatusBadge, Wbgt, nowLocalInput, useHeatCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
const PAGE_SIZE = 50;

/* ═════════════ welfare checks register (§3.8, RS-1…RS-4) ═════════════ */

export function WelfareChecksPage() {
  return <ProjectGate>{(p) => <Checks project={p} />}</ProjectGate>;
}

function Checks({ project }: { project: Project }) {
  const t = useTranslations("heat.welfare");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const station = s.get("station") ?? "";
  const day = s.get("day") ?? "";
  const stations = useRestStations(project.id, { page_size: 200 }, { enabled: caps.view });
  const q = useWelfareChecks(project.id, { station_id: station || null, day: day || null, page, page_size: PAGE_SIZE }, { enabled: caps.view });
  const [voiding, setVoiding] = useState<S["WelfareCheckRead"] | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.welfare ? (
            <Button asChild>
              <Link href="/heat-welfare-checks/new" data-testid="new-check">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <HeatFieldSubNav />
      <ListToolbar>
        <SelectFilter id="wc-station" label={t("station")} value={station} onChange={(v) => s.set({ station: v })} options={(stations.data?.items ?? []).map((x) => ({ value: x.id, label: x.station_code }))} />
        <DateFilter id="wc-day" label={t("day")} value={day} onChange={(v) => s.set({ day: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="checks-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("station")}</TH>
                <TH>{t("checkedAt")}</TH>
                <TH>{t("result")}</TH>
                <TH>{t("water")}</TH>
                <TH>{t("ca")}</TH>
                <TH>{tc("status")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((c) => {
                const fails = c.items.filter((i) => i.answer === "fail").map((i) => i.item);
                return (
                  <TR key={c.id} data-testid="check-row" data-no={c.check_no} data-critical={c.critical_fail ? "yes" : "no"}>
                    <TD label={t("no")}>
                      <Code className="font-medium">{c.check_no}</Code>
                    </TD>
                    <TD label={t("station")}>
                      <Code>{c.station_code}</Code>
                    </TD>
                    <TD label={t("checkedAt")}>
                      <StackedDate v={c.checked_at} time projectId={project.id} />
                      <span className="block text-xs text-muted-foreground">
                        <UserName u={c.checked_by} />
                      </span>
                    </TD>
                    <TD label={t("result")}>
                      {c.critical_fail ? (
                        <Badge tone="danger">
                          <AlertTriangle aria-hidden />
                          {t("criticalFail")}
                        </Badge>
                      ) : fails.length ? (
                        <Badge tone="warning">
                          <AlertTriangle aria-hidden />
                          {t("someFail")}
                        </Badge>
                      ) : (
                        <Badge tone="success">
                          <CheckCircle2 aria-hidden />
                          {t("allPass")}
                        </Badge>
                      )}
                      {fails.length ? <bdi className="ltr block text-xs text-muted-foreground">{fails.join(", ")}</bdi> : null}
                    </TD>
                    <TD label={t("water")}>{c.water_temp_c ? <Wbgt v={c.water_temp_c} /> : "—"}</TD>
                    <TD label={t("ca")}>{c.ca_refs.length ? c.ca_refs.map((r) => <Code key={r} className="block text-xs">{r}</Code>) : "—"}</TD>
                    <TD label={tc("status")}>
                      <RecordStatusBadge status={c.status} />
                    </TD>
                    <TD>
                      {caps.void && c.status === "valid" ? (
                        <Button size="sm" variant="destructive-outline" onClick={() => setVoiding(c)} data-testid="check-void">
                          {t("void")}
                        </Button>
                      ) : null}
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={station || day ? undefined : t("empty")} />
      )}
      {voiding ? (
        <HeatReasonDialog
          title={t("voidTitle", { no: voiding.check_no })}
          confirmLabel={t("void")}
          onConfirm={async (reason) => {
            await unwrap(api.POST("/api/v1/heat-welfare-checks/{check_id}/void", { params: { path: { check_id: voiding.id } }, body: { reason } }));
          }}
          onClose={() => setVoiding(null)}
        />
      ) : null}
    </div>
  );
}

/* ═════════════ new welfare check (phone-first, every HW item answered) ═════════════ */

export function NewWelfareCheckPage() {
  return <ProjectGate>{(p) => <NewCheck project={p} />}</ProjectGate>;
}

type Answers = Partial<Record<S["WelfareItem"], { answer: S["CheckAnswer"]; note: string }>>;

function NewCheck({ project }: { project: Project }) {
  const t = useTranslations("heat.welfare");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const caps = useHeatCaps(project.id);
  const refresh = useHeatRefresh();
  const opts = useProjectOptions(project.id);
  const ref = useHeatReference();
  const stations = useRestStations(project.id, { page_size: 200 }, { enabled: caps.welfare });
  const active = (stations.data?.items ?? []).filter((x) => x.active);
  const s = useSearchState();
  const [station, setStation] = useState(s.get("station") ?? "");
  const [at, setAt] = useState(nowLocalInput());
  const [eng, setEng] = useState("");
  const [water, setWater] = useState("");
  const [persons, setPersons] = useState("");
  const [answers, setAnswers] = useState<Answers>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<S["WelfareCheckRead"] | null>(null);
  if (!caps.welfare) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const meta = (code: string) => ref.data?.welfare_items.find((x) => x.code === code);
  const all = WELFARE_ITEMS.every((i) => answers[i]);
  const ready = Boolean(station && at && all);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(
        api.POST("/api/v1/projects/{project_id}/heat-welfare-checks", {
          params: { path: { project_id: project.id } },
          body: {
            station_id: station,
            checked_at: zonedInputToUtc(at),
            engagement_id: eng || null,
            water_temp_c: water || null,
            persons_present: persons ? Number(persons) : null,
            items: WELFARE_ITEMS.map((i) => ({ item: i, answer: answers[i]!.answer, note: answers[i]!.note.trim() || null })),
          },
        }),
      );
      await refresh();
      setDone(r);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="mx-auto flex max-w-xl flex-col gap-4" data-testid="check-saved" data-no={done.check_no} data-critical={done.critical_fail ? "yes" : "no"}>
        <PageHeader title={t("savedTitle", { no: done.check_no })} />
        {done.critical_fail ? (
          <Alert tone="danger" data-testid="check-ca">
            {t("caRaised", { refs: done.ca_refs.join(", ") || "—" })}
          </Alert>
        ) : (
          <Alert tone="success">{t("savedOk")}</Alert>
        )}
        <ApiWarnings warnings={done.warnings} />
        <div className="grid gap-2 sm:flex">
          <Button asChild className="min-h-12 sm:min-h-control">
            <Link href="/heat-welfare-checks">{t("toList")}</Link>
          </Button>
          <Button variant="outline" className="min-h-12 sm:min-h-control" onClick={() => router.push("/heat-board")}>
            {t("toBoard")}
          </Button>
        </div>
      </div>
    );
  }

  const big = "h-12 text-base sm:h-control sm:text-sm";
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <PageHeader title={t("new")} description={t("newHint")} />
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="wc-st" label={t("station")} required>
          <Select id="wc-st" className={big} value={station} onChange={(e) => setStation(e.target.value)} data-testid="wc-station">
            <option value="">{tc("select")}</option>
            {active.map((x) => (
              <option key={x.id} value={x.id}>
                {x.station_code} — {x.zone_codes.join(", ")}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="wc-at" label={t("checkedAt")} required>
          <Input id="wc-at" type="datetime-local" dir="ltr" className={big} value={at} onChange={(e) => setAt(e.target.value)} data-testid="wc-at" />
        </FormField>
        <FormField id="wc-eng" label={t("engagement")} hint={t("engagementHint")}>
          <Select id="wc-eng" className={big} value={eng} onChange={(e) => setEng(e.target.value)}>
            <option value="">—</option>
            {opts.engagements.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </Select>
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField id="wc-water" label={t("waterTemp")} hint={t("waterHint")}>
            <DecimalInput id="wc-water" value={water} onChange={setWater} className={big} data-testid="wc-water" />
          </FormField>
          <FormField id="wc-persons" label={t("persons")}>
            <Input id="wc-persons" inputMode="numeric" dir="ltr" className={big} value={persons} onChange={(e) => setPersons(e.target.value.replace(/[^0-9]/g, ""))} />
          </FormField>
        </div>
      </div>
      <Button
        type="button"
        variant="outline"
        className="min-h-12 self-start sm:min-h-control"
        onClick={() => setAnswers(Object.fromEntries(WELFARE_ITEMS.map((i) => [i, { answer: "pass", note: answers[i]?.note ?? "" }])) as Answers)}
        data-testid="wc-all-pass"
      >
        <CheckCircle2 aria-hidden />
        {t("allPassBtn")}
      </Button>
      <ol className="flex flex-col divide-y rounded-md border" data-testid="wc-items">
        {WELFARE_ITEMS.map((i) => {
          const m = meta(i);
          const a = answers[i];
          const choices = (["pass", "fail", "na"] as const).filter((x) => x !== "na" || m?.na_allowed);
          return (
            <li key={i} className="flex flex-col gap-2 p-3" data-testid="wc-item" data-item={i} data-answer={a?.answer ?? ""}>
              <p className="flex items-start gap-2 text-sm">
                <Code className="font-semibold">{i}</Code>
                <span className="flex-1">{m ? (locale === "ar" ? m.label_ar : m.label_en) : te(`welfareItem.${i}`)}</span>
                {m?.critical ? (
                  <Badge tone="danger" title={t("critical")}>
                    <Star aria-hidden />
                    {t("critical")}
                  </Badge>
                ) : null}
              </p>
              <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={i}>
                {choices.map((c) => (
                  <Button
                    key={c}
                    type="button"
                    role="radio"
                    aria-checked={a?.answer === c}
                    variant={a?.answer === c ? (c === "fail" ? "destructive" : "default") : "outline"}
                    className={cn("min-h-12 sm:min-h-control")}
                    onClick={() => setAnswers({ ...answers, [i]: { answer: c, note: a?.note ?? "" } })}
                    data-testid={`wc-${i}-${c}`}
                  >
                    <ChoiceMark on={a?.answer === c} />
                    {te(`checkAnswer.${c}`)}
                  </Button>
                ))}
              </div>
              {a?.answer === "fail" ? (
                <Input placeholder={t("notePlaceholder")} value={a.note} maxLength={300} onChange={(e) => setAnswers({ ...answers, [i]: { answer: "fail", note: e.target.value } })} />
              ) : null}
            </li>
          );
        })}
      </ol>
      {!all ? <p className="text-xs text-muted-foreground">{t("answerAll")}</p> : null}
      <MutationError error={error} />
      <Button className="min-h-12 text-base sm:min-h-control sm:text-sm" disabled={!ready || busy} onClick={() => void save()} data-testid="wc-save">
        {busy ? tc("saving") : t("save")}
      </Button>
    </div>
  );
}
