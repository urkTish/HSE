"use client";
import { Ban, Camera, CheckCircle2, Hourglass, Megaphone, PenLine, Plus, ScanLine, Send, Trash2, UserPlus, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { UserSelect, useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { CameraScanner } from "@/components/gate/gate-check";
import { StackedDate } from "@/components/medical/common";
import { DateFilter } from "@/components/training/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useCampaign, useCampaigns, useFieldRefresh, useFieldSettings, useToolboxSuggestions, useToolboxTalk, useToolboxTalks, useTopics } from "@/lib/api/field";
import { CAMPAIGN_STATUSES, TALK_SHIFTS, TALK_STATUSES, WORKER_LANGUAGES } from "@/lib/field-enums";
import { cacheHoursOf, downloadPack, newUuid, submitWithOutbox, useFieldOffline } from "@/lib/field-offline";
import { useOnline } from "@/lib/local-draft";
import { useSearchState } from "@/lib/url-state";
import { fromLocalInput, nowLocal } from "@/components/emergency/common";
import { CampaignStatusBadge, FieldReasonDialog, FieldTalkSubNav, NoNamesHint, OfflineLabel, PhotoPicker, SignaturePad, TalkStatusBadge, useBi, useFieldCaps, useFieldRef } from "./common";
import { OfflinePackCard, OutboxPanel } from "./offline";

type S = Schemas;
type Project = S["ProjectRead"];
type Dep = S["OfflineDeployment"];

/* ═════════════ talk register (§3.11, TBT-3…TBT-9) ═════════════ */

export function ToolboxTalksPage() {
  return <ProjectGate>{(p) => <Talks project={p} />}</ProjectGate>;
}

function Talks({ project }: { project: Project }) {
  const t = useTranslations("field.talks");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useFieldCaps(project.id);
  const opts = useProjectOptions(project.id);
  const bi = useBi();
  const s = useSearchState();
  const site = s.get("site") ?? "";
  const host = s.get("host") ?? "";
  const status = (s.get("status") ?? "") as S["TalkStatus"] | "";
  const from = s.get("from") ?? "";
  const to = s.get("to") ?? "";
  const topic = s.get("topic") ?? "";
  const page = Number(s.get("page") ?? 1);
  const q = useToolboxTalks(project.id, { site_id: site || null, host_engagement_id: host || null, status: status ? [status] : null, date_from: from || null, date_to: to || null, topic_code: topic || null, page, page_size: 50 }, { enabled: caps.view || caps.talk });
  if (!caps.view && !caps.talk) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.talk ? (
            <Button asChild>
              <Link href="/toolbox-talks/new" data-testid="talk-new">
                <Plus aria-hidden />
                {t("record")}
              </Link>
            </Button>
          ) : null
        }
      />
      <FieldTalkSubNav />
      <OutboxPanel kind="talk" projectId={project.id} />
      <ListToolbar>
        <SelectFilter id="tk-site" label={t("site")} value={site} onChange={(v) => s.set({ site: v, page: null })} options={opts.sites.map((x) => ({ value: x.value, label: x.code }))} />
        <SelectFilter id="tk-host" label={t("host")} value={host} onChange={(v) => s.set({ host: v, page: null })} options={opts.engagements.map((x) => ({ value: x.value, label: x.label }))} />
        <SelectFilter id="tk-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={TALK_STATUSES.map((x) => ({ value: x, label: te(`fdTalkStatus.${x}`) }))} />
        <DateFilter id="tk-from" label={t("from")} value={from} onChange={(v) => s.set({ from: v, page: null })} />
        <DateFilter id="tk-to" label={t("to")} value={to} onChange={(v) => s.set({ to: v, page: null })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data?.items.length ? (
        <>
          <Table data-testid="talks-table">
            <THead>
              <TR>
                <TH>{t("talk")}</TH>
                <TH>{t("delivered")}</TH>
                <TH>{t("where")}</TH>
                <TH>{t("topics")}</TH>
                <TH>{t("language")}</TH>
                <TH className="text-end">{t("attendance")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {q.data.items.map((x) => (
                <TR key={x.id} data-testid="talk-row" data-no={x.talk_no} data-status={x.status}>
                  <TD label={t("talk")}>
                    <Link href={`/toolbox-talks/${x.id}`} className="font-medium text-primary hover:underline">
                      <Code>{x.talk_no}</Code>
                    </Link>
                    <OfflineLabel show={x.recorded_offline} />
                  </TD>
                  <TD label={t("delivered")}>
                    <StackedDate v={x.delivered_at} time projectId={project.id} />
                  </TD>
                  <TD label={t("where")}>
                    {x.site.code}
                    {x.zones.length ? ` · ${x.zones.map((z) => z.code).join(", ")}` : ""}
                    {x.host_engagement ? <span className="block text-xs text-muted-foreground">{x.host_engagement.short_code}</span> : null}
                  </TD>
                  <TD label={t("topics")}>
                    {x.topics.map((tp, i) => (
                      <span key={i} className="block text-sm">
                        {tp.topic_code ? <Code className="me-1">{tp.topic_code}</Code> : null}
                        {bi(tp.title_en, tp.title_ar)}
                      </span>
                    ))}
                  </TD>
                  <TD label={t("language")}>
                    {te(`fdLanguage.${x.language}`)}
                    {x.interpreter_languages.length ? <span className="block text-xs text-muted-foreground">+ {x.interpreter_languages.map((l) => te(`fdLanguage.${l}`)).join(", ")}</span> : null}
                  </TD>
                  <TD label={t("attendance")} className="text-end tabular-nums">
                    <span data-testid="talk-counts">{t("counts", { named: x.named_count, briefed: x.briefed_count, unnamed: x.unnamed_count })}</span>
                  </TD>
                  <TD label={tc("status")}>
                    <TalkStatusBadge status={x.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={50} total={q.data.total} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
    </div>
  );
}

/* ═════════════ record a talk on the phone (TBT-3…TBT-9, EXE-6) ═════════════ */

interface Row {
  key: string;
  method: S["AttendanceMethod"];
  deployment?: Dep | null;
  token?: string;
  signature?: S["PhotoInput"] | null;
}

/** Display only: the server decides understood_language (TBT-6); this mirrors it so the recorder sees mismatches early. */
function understood(d: Dep | null | undefined, lang: string, interp: string[]): "talk_language" | "interpreter" | "none" | null {
  if (!d) return null;
  if (d.primary_language === lang) return "talk_language";
  if (interp.includes(d.primary_language)) return "interpreter";
  return "none";
}

export function TalkRecordPage() {
  return <ProjectGate>{(p) => <Record project={p} />}</ProjectGate>;
}

function Record({ project }: { project: Project }) {
  const t = useTranslations("field.talks");
  const tc = useTranslations("common");
  const caps = useFieldCaps(project.id);
  const online = useOnline();
  const { packs, loaded } = useFieldOffline();
  const [done, setDone] = useState<{ talk: S["TalkRead"] } | { queued: string } | null>(null);
  const [key, setKey] = useState(0);
  const has = Boolean(packs[project.id]);
  // The attendance list comes from the offline pack (P6d-6: no ID numbers, no card tokens): fetch it once if missing.
  useEffect(() => {
    if (caps.talk && loaded && !has && online) void downloadPack(project.id).catch(() => undefined);
  }, [caps.talk, loaded, has, online, project.id]);
  if (!caps.talk) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={t("recordTitle")} description={t("recordSubtitle")} />
      <FieldTalkSubNav />
      <OutboxPanel kind="talk" projectId={project.id} />
      {done ? (
        <TalkDone
          d={done}
          onAgain={() => {
            setDone(null);
            setKey(key + 1);
          }}
        />
      ) : (
        <>
          <div className="mb-4">
            <OfflinePackCard projectId={project.id} />
          </div>
          <TalkForm key={key} project={project} onDone={setDone} />
        </>
      )}
    </div>
  );
}

function TalkForm({ project, onDone }: { project: Project; onDone: (d: { talk: S["TalkRead"] } | { queued: string }) => void }) {
  const t = useTranslations("field.talks");
  const te = useTranslations("enums");
  const bi = useBi();
  const { label, items: refItems } = useFieldRef();
  const caps = useFieldCaps(project.id);
  const opts = useProjectOptions(project.id);
  const settings = useFieldSettings(project.id);
  const { packs } = useFieldOffline();
  const pack = packs[project.id]?.pack;
  const live = useTopics({ status: ["published"] });
  const topics = live.data?.items ?? pack?.topics.filter((x) => x.status === "published") ?? [];
  const [site, setSite] = useState("");
  const [zones, setZones] = useState<string[]>([]);
  const [host, setHost] = useState("");
  const [shift, setShift] = useState<S["TalkShift"]>("day");
  const [late, setLate] = useState(false);
  const [at, setAt] = useState(nowLocal());
  const [duration, setDuration] = useState("15");
  const [presenterKind, setPresenterKind] = useState<"me" | "user" | "deployment">("me");
  const [presenterUser, setPresenterUser] = useState("");
  const [presenterDep, setPresenterDep] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [freeEn, setFreeEn] = useState("");
  const [freeCat, setFreeCat] = useState("general");
  const [lang, setLang] = useState<S["WorkerLanguage"]>("ur");
  const [interp, setInterp] = useState<S["WorkerLanguage"][]>([]);
  const [campaign, setCampaign] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [unnamed, setUnnamed] = useState("0");
  const [sheets, setSheets] = useState<S["PhotoInput"][]>([]);
  const [questions, setQuestions] = useState("");
  const [clientUuid] = useState(newUuid);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const sugg = useToolboxSuggestions(project.id, { site_id: site, host_engagement_id: host });
  const campaigns = useCampaigns(project.id, { status: ["issued"], page_size: 100 });
  const pickedTopics = topics.filter((x) => picked.includes(x.id));
  const campaignChoices = (campaigns.data?.items ?? []).filter((c) => pickedTopics.some((p) => p.topic_code === c.topic_code));
  const min = settings.data?.tbt_min_minutes ?? 10;
  const named = rows.length;
  const needsSheet = (Number(unnamed) || 0) > 0 || rows.some((r) => r.method === "list" && !r.signature);
  const topicCount = picked.length + (freeEn.trim() ? 1 : 0);
  const dur = Number(duration);
  const valid = site && host && topicCount >= 1 && topicCount <= 3 && dur >= 5 && dur <= 120 && (!needsSheet || sheets.length > 0) && (named > 0 || Number(unnamed) > 0) && (presenterKind === "me" || (presenterKind === "user" ? presenterUser : presenterDep));

  async function submit() {
    setBusy(true);
    setError(null);
    const body: S["TalkCreate"] = {
      client_uuid: clientUuid,
      site_id: site,
      zone_ids: zones,
      host_engagement_id: host,
      shift,
      delivered_at: late ? (fromLocalInput(at) ?? new Date().toISOString()) : new Date().toISOString(),
      duration_minutes: dur,
      presenter_user_id: presenterKind === "me" ? caps.meId : presenterKind === "user" ? presenterUser : null,
      presenter_deployment_id: presenterKind === "deployment" ? presenterDep : null,
      topics: [...picked.map((id) => ({ topic_id: id })), ...(freeEn.trim() ? [{ free_title_en: freeEn.trim(), category: freeCat as S["TopicCategory"] }] : [])],
      language: lang,
      interpreter_languages: interp,
      campaign_id: campaign || null,
      attendance: rows.map((r) => (r.method === "card_scan" ? { method: "card_scan" as const, scanned_token: r.token ?? null, signature: r.signature ?? null } : { method: "list" as const, deployment_id: r.deployment?.deployment_id ?? null, signature: r.signature ?? null })),
      unnamed_count: Number(unnamed) || 0,
      sheet_photos: sheets,
      questions_raised: questions.trim() || null,
    };
    const lab = `${opts.sites.find((x) => x.value === site)?.code ?? ""} · ${opts.engagements.find((x) => x.value === host)?.code ?? ""} · ${named + (Number(unnamed) || 0)}`;
    const res = await submitWithOutbox<S["TalkRead"]>("talk", project.id, body, lab, cacheHoursOf(pack));
    setBusy(false);
    if (res.status === "sent") onDone({ talk: res.record });
    else if (res.status === "queued") onDone({ queued: lab });
    else setError(res.error);
  }

  return (
    <div className="flex flex-col gap-4" data-testid="talk-form">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("whereWho")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <FormField id="tf-site" label={t("site")} required>
            <Select value={site} onChange={(e) => (setSite(e.target.value), setZones([]))} data-testid="tf-site">
              <option value="">—</option>
              {opts.sites.map((x) => (
                <option key={x.value} value={x.value}>
                  {x.code}
                </option>
              ))}
            </Select>
          </FormField>
          <MultiSelect id="tf-zones" label={t("zones")} options={opts.zones.filter((z) => z.siteId === site).map((z) => ({ value: z.value, label: z.label }))} value={zones} onChange={setZones} allLabel={t("noZone")} className="lg:w-full" />
          <FormField id="tf-host" label={t("host")} required>
            <Select value={host} onChange={(e) => setHost(e.target.value)} data-testid="tf-host">
              <option value="">—</option>
              {opts.engagements
                .filter((e) => !site || e.siteIds.includes(site))
                .map((e) => (
                  <option key={e.value} value={e.value}>
                    {e.label}
                  </option>
                ))}
            </Select>
          </FormField>
          <FormField id="tf-shift" label={t("shift")} required>
            <Select value={shift} onChange={(e) => setShift(e.target.value as S["TalkShift"])}>
              {TALK_SHIFTS.map((x) => (
                <option key={x} value={x}>
                  {te(`fdShift.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="tf-dur" label={t("duration")} required hint={dur < min ? t("shortHint", { min }) : undefined}>
            <Input type="number" inputMode="numeric" className="ltr w-28" min={5} max={120} value={duration} onChange={(e) => setDuration(e.target.value)} data-testid="tf-duration" />
          </FormField>
          <FormField id="tf-late" label={t("deliveredAt")} hint={t("deliveredHint")}>
            <span className="flex flex-wrap items-center gap-2">
              <Button type="button" variant={late ? "outline" : "default"} size="sm" className="min-h-11" onClick={() => setLate(false)}>
                {t("now")}
              </Button>
              <Button type="button" variant={late ? "default" : "outline"} size="sm" className="min-h-11" onClick={() => setLate(true)} data-testid="tf-late">
                {t("earlier")}
              </Button>
              {late ? <Input type="datetime-local" className="w-56" value={at} onChange={(e) => setAt(e.target.value)} data-testid="tf-at" /> : null}
            </span>
          </FormField>
          <FormField id="tf-presenter" label={t("presenter")} required>
            <Select value={presenterKind} onChange={(e) => setPresenterKind(e.target.value as "me" | "user" | "deployment")} data-testid="tf-presenter">
              <option value="me">{t("presenterMe")}</option>
              <option value="user">{t("presenterUser")}</option>
              <option value="deployment">{t("presenterWorker")}</option>
            </Select>
          </FormField>
          {presenterKind === "user" ? (
            <FormField id="tf-puser" label={t("presenterUser")} required>
              <UserSelect projectId={project.id} value={presenterUser} onChange={(e) => setPresenterUser(e.target.value)} />
            </FormField>
          ) : presenterKind === "deployment" ? (
            <FormField id="tf-pdep" label={t("presenterWorker")} required>
              <DeploymentSelect deployments={pack?.deployments ?? []} engagementId={host} value={presenterDep} onChange={setPresenterDep} />
            </FormField>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("topicsTitle")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("topicsHint")}</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {sugg.data?.items.length ? (
            <div data-testid="suggestions">
              <p className="mb-1 text-sm font-medium">{t("suggested")}</p>
              <ul className="flex flex-col gap-2">
                {sugg.data.items.map((x) => {
                  const on = picked.includes(x.topic_id);
                  return (
                    <li key={x.topic_id}>
                      <Button
                        type="button"
                        variant={on ? "default" : "outline"}
                        className="h-auto min-h-11 w-full justify-start gap-2 py-2 text-start whitespace-normal"
                        onClick={() => setPicked(on ? picked.filter((p) => p !== x.topic_id) : [...picked, x.topic_id].slice(0, 3))}
                        data-testid="suggestion"
                        data-code={x.topic_code}
                        data-source={x.source}
                      >
                        {on ? <CheckCircle2 aria-hidden /> : <Plus aria-hidden />}
                        <Code>{x.topic_code}</Code>
                        <span className="flex-1">{bi(x.title_en, x.title_ar)}</span>
                        <Badge tone={x.source === "campaign" ? "warning" : "neutral"}>
                          {te(`fdSuggestionSource.${x.source}`)}
                          {x.reason_ref ? ` · ${x.reason_ref}` : ""}
                        </Badge>
                        {x.delivered_recently ? <span className="text-xs opacity-80">{t("recently")}</span> : null}
                      </Button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
          <MultiSelect
            id="tf-topics"
            label={t("library")}
            options={topics.map((x) => ({ value: x.id, label: `${x.topic_code} · ${bi(x.title_en, x.title_ar)}${x.review_overdue ? ` (${t("reviewOverdue")})` : ""}` }))}
            value={picked}
            onChange={(v) => setPicked(v.slice(0, 3))}
            allLabel={t("noneChosen")}
            className="lg:w-full"
            testId="tf-topics"
          />
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField id="tf-free" label={t("freeTitle")} className="sm:col-span-2">
              <Input maxLength={150} value={freeEn} onChange={(e) => setFreeEn(e.target.value)} />
            </FormField>
            <FormField id="tf-freecat" label={t("category")}>
              <Select value={freeCat} onChange={(e) => setFreeCat(e.target.value)}>
                {refItems("topic_categories").map((c) => (
                  <option key={c.code} value={c.code}>
                    {label("topic_categories", c.code)}
                  </option>
                ))}
              </Select>
            </FormField>
          </div>
          {campaignChoices.length ? (
            <FormField id="tf-campaign" label={t("campaign")}>
              <Select value={campaign} onChange={(e) => setCampaign(e.target.value)} data-testid="tf-campaign">
                <option value="">—</option>
                {campaignChoices.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.campaign_no} · {c.topic_code}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="tf-lang" label={t("language")} required>
              <Select value={lang} onChange={(e) => setLang(e.target.value as S["WorkerLanguage"])} data-testid="tf-lang">
                {WORKER_LANGUAGES.map((l) => (
                  <option key={l} value={l}>
                    {te(`fdLanguage.${l}`)}
                  </option>
                ))}
              </Select>
            </FormField>
            <MultiSelect id="tf-interp" label={t("interpreters")} options={WORKER_LANGUAGES.filter((l) => l !== lang).map((l) => ({ value: l, label: te(`fdLanguage.${l}`) }))} value={interp} onChange={setInterp} allLabel={t("noInterpreter")} className="lg:w-full" testId="tf-interp" />
          </div>
        </CardContent>
      </Card>

      <Attendance rows={rows} setRows={setRows} deployments={pack?.deployments ?? []} host={host} lang={lang} interp={interp} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("evidence")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <FormField id="tf-unnamed" label={t("unnamed")} hint={t("unnamedHint")}>
            <Input type="number" inputMode="numeric" className="ltr w-28" min={0} max={200} value={unnamed} onChange={(e) => setUnnamed(e.target.value)} data-testid="tf-unnamed" />
          </FormField>
          <div>
            <p className="mb-1 text-sm font-medium">
              {t("sheetPhotos")}
              {needsSheet ? <span className="text-danger"> *</span> : null}
            </p>
            <PhotoPicker value={sheets} onChange={setSheets} max={4} testId="tf-sheet" required={needsSheet} />
            {needsSheet && !sheets.length ? (
              <p className="mt-1 text-xs text-warning" data-testid="sheet-needed">
                {t("sheetNeeded")}
              </p>
            ) : null}
          </div>
          <FormField id="tf-q" label={t("questions")} hint={<NoNamesHint />}>
            <Textarea maxLength={1000} value={questions} onChange={(e) => setQuestions(e.target.value)} />
          </FormField>
        </CardContent>
      </Card>
      <MutationError error={error} />
      <Button className="min-h-12 text-base" disabled={busy || !valid} onClick={() => void submit()} data-testid="tf-submit">
        {busy ? t("sending") : t("submit", { n: named + (Number(unnamed) || 0) })}
      </Button>
    </div>
  );
}

function DeploymentSelect({ deployments, engagementId, value, onChange }: { deployments: Dep[]; engagementId: string; value: string; onChange: (v: string) => void }) {
  const bi = useBi();
  const list = deployments.filter((d) => !engagementId || d.engagement_id === engagementId).slice(0, 300);
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">—</option>
      {list.map((d) => (
        <option key={d.deployment_id} value={d.deployment_id}>
          {d.worker_no} · {bi(d.name_en, d.name_ar)}
        </option>
      ))}
    </Select>
  );
}

/** Named attendance: card scans (camera or pasted payload) and picks from the crew list with an optional signature. */
function Attendance({ rows, setRows, deployments, host, lang, interp }: { rows: Row[]; setRows: (r: Row[]) => void; deployments: Dep[]; host: string; lang: string; interp: string[] }) {
  const t = useTranslations("field.talks");
  const te = useTranslations("enums");
  const bi = useBi();
  const [camera, setCamera] = useState(false);
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [allEng, setAllEng] = useState(false);
  const [signing, setSigning] = useState<string | null>(null);
  const chosen = useMemo(() => new Set(rows.map((r) => r.deployment?.deployment_id).filter(Boolean)), [rows]);
  const tokens = new Set(rows.map((r) => r.token).filter(Boolean));
  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    return deployments
      .filter((d) => (allEng || !host || d.engagement_id === host) && !chosen.has(d.deployment_id))
      .filter((d) => !q || d.worker_no.toLowerCase().includes(q) || d.name_en.toLowerCase().includes(q) || d.name_ar.includes(search.trim()) || d.trade.toLowerCase().includes(q))
      .slice(0, 30);
  }, [deployments, host, allEng, search, chosen]);
  function addToken(p: string) {
    const v = p.trim();
    if (!v || tokens.has(v)) {
      if (v) toast.warning(t("alreadyScanned"));
      return;
    }
    setRows([...rows, { key: newUuid(), method: "card_scan", token: v }]);
    toast.success(t("scanned"));
  }
  const mismatch = rows.filter((r) => understood(r.deployment, lang, interp) === "none").length;
  return (
    <Card data-testid="attendance">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("attendanceTitle")}</CardTitle>
        <span className="text-sm font-semibold tabular-nums" data-testid="att-count">
          {t("namedN", { n: rows.length })}
        </span>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-xs text-muted-foreground">{t("scanPurpose")}</p>
        <div className="flex flex-col gap-2">
          <Button type="button" className="min-h-12 text-base" onClick={() => setCamera(true)} data-testid="att-camera">
            <Camera aria-hidden />
            {t("scanCard")}
          </Button>
          {camera ? <CameraScanner onResult={(p) => addToken(p)} onClose={() => setCamera(false)} paused={false} /> : null}
          <div className="flex gap-2">
            <Input className="ltr" placeholder="HSE2:AC:…" aria-label={t("payload")} value={typed} onChange={(e) => setTyped(e.target.value)} data-testid="att-payload" />
            <Button type="button" variant="outline" className="min-h-11" disabled={!typed.trim()} onClick={() => (addToken(typed), setTyped(""))} data-testid="att-payload-go">
              <ScanLine aria-hidden />
              {t("add")}
            </Button>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-end gap-2">
            <FormField id="att-search" label={t("pickFromList")} className="flex-1">
              <Input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("searchHint")} data-testid="att-search" />
            </FormField>
            <Button type="button" variant="ghost" size="sm" className="min-h-11" onClick={() => setAllEng(!allEng)}>
              {allEng ? t("hostOnly") : t("allContractors")}
            </Button>
          </div>
          {!deployments.length ? <p className="text-xs text-muted-foreground">{t("noList")}</p> : null}
          {search.trim() || !host ? (
            <ul className="flex max-h-72 flex-col divide-y overflow-y-auto rounded-md border" data-testid="att-matches">
              {matches.map((d) => (
                <li key={d.deployment_id}>
                  <button
                    type="button"
                    className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-start text-sm hover:bg-muted"
                    onClick={() => (setRows([...rows, { key: newUuid(), method: "list", deployment: d }]), setSearch(""))}
                    data-testid="att-match"
                    data-worker={d.worker_no}
                  >
                    <UserPlus aria-hidden className="size-4 shrink-0" />
                    <Code>{d.worker_no}</Code>
                    <span className="flex-1">{bi(d.name_en, d.name_ar)}</span>
                    <span className="text-xs text-muted-foreground">
                      {d.trade} · {te(`fdLanguage.${d.primary_language}`)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        {rows.length ? (
          <ul className="flex flex-col divide-y rounded-md border" data-testid="att-rows">
            {rows.map((r) => {
              const u = understood(r.deployment, lang, interp);
              return (
                <li key={r.key} className="flex flex-col gap-2 p-3 text-sm" data-testid="att-row" data-method={r.method} data-signed={r.signature ? "yes" : "no"}>
                  <div className="flex flex-wrap items-center gap-2">
                    {r.method === "card_scan" ? (
                      <Badge tone="info">
                        <ScanLine aria-hidden />
                        {t("cardScan")}
                      </Badge>
                    ) : (
                      <Badge tone="neutral">{t("fromList")}</Badge>
                    )}
                    <span className="flex-1">
                      {r.deployment ? (
                        <>
                          <Code>{r.deployment.worker_no}</Code> {bi(r.deployment.name_en, r.deployment.name_ar)}
                        </>
                      ) : (
                        <span className="text-muted-foreground">
                          {t("cardRef")} <Code>…{(r.token ?? "").slice(-6)}</Code>
                        </span>
                      )}
                    </span>
                    {u === "none" ? (
                      <Badge tone="warning" data-testid="lang-mismatch">
                        {t("langMismatch")}
                      </Badge>
                    ) : u === "interpreter" ? (
                      <Badge tone="info">{te("fdUnderstood.interpreter")}</Badge>
                    ) : null}
                    {r.signature ? (
                      <Badge tone="success">
                        <PenLine aria-hidden />
                        {t("signed")}
                      </Badge>
                    ) : r.method === "list" ? (
                      <Button type="button" size="sm" variant="outline" className="min-h-11" onClick={() => setSigning(r.key)} data-testid="att-sign">
                        <PenLine aria-hidden />
                        {t("sign")}
                      </Button>
                    ) : null}
                    <Button type="button" size="sm" variant="ghost" className="min-h-11" onClick={() => setRows(rows.filter((x) => x.key !== r.key))} aria-label={t("removeRow")}>
                      <Trash2 aria-hidden />
                    </Button>
                  </div>
                  {signing === r.key ? <SignaturePad onDone={(p) => (setRows(rows.map((x) => (x.key === r.key ? { ...x, signature: p } : x))), setSigning(null))} onCancel={() => setSigning(null)} /> : null}
                </li>
              );
            })}
          </ul>
        ) : null}
        {mismatch ? (
          <Alert tone="warning" data-testid="mismatch-note">
            {t("mismatchNote", { n: mismatch })}
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

function TalkDone({ d, onAgain }: { d: { talk: S["TalkRead"] } | { queued: string }; onAgain: () => void }) {
  const t = useTranslations("field.talks");
  const router = useRouter();
  if ("queued" in d) {
    return (
      <div className="flex flex-col gap-4" data-testid="talk-queued">
        <div className="rounded-md border-2 border-warning/50 bg-warning-bg p-4 text-warning">
          <p className="flex items-center gap-2 text-xl font-bold">
            <Hourglass aria-hidden className="size-7" />
            {t("queuedTitle")}
          </p>
          <p className="mt-1 text-sm text-foreground">{t("queuedText", { label: d.queued })}</p>
        </div>
        <Button className="min-h-12 text-base" onClick={onAgain}>
          {t("again")}
        </Button>
      </div>
    );
  }
  const x = d.talk;
  return (
    <div className="flex flex-col gap-4" data-testid="talk-saved" data-no={x.talk_no}>
      <div className="rounded-md border-2 border-success/40 bg-success-bg p-4 text-success">
        <p className="flex items-center gap-2 text-xl font-bold">
          <CheckCircle2 aria-hidden className="size-7" />
          {t("savedTitle")}
        </p>
        <p className="mt-1 text-sm text-foreground">
          <Code>{x.talk_no}</Code> · {t("counts", { named: x.named_count, briefed: x.briefed_count, unnamed: x.unnamed_count })}
        </p>
      </div>
      <RejectedRows rows={x.rejected_rows} />
      <ApiWarnings warnings={x.warnings} />
      <div className="flex flex-wrap gap-2">
        <Button className="min-h-12 text-base" variant="outline" onClick={() => router.push(`/toolbox-talks/${x.id}`)} data-testid="talk-open">
          {t("open")}
        </Button>
        <Button className="min-h-12 text-base" onClick={onAgain} data-testid="talk-again">
          {t("again")}
        </Button>
      </div>
    </div>
  );
}

function RejectedRows({ rows }: { rows: S["RejectedRow"][] }) {
  const t = useTranslations("field.talks");
  const te = useTranslations("errors");
  if (!rows.length) return null;
  return (
    <Alert tone="warning" data-testid="rejected-rows">
      <span className="font-semibold">{t("rejected", { n: rows.length })}</span>
      <ul className="mt-1 list-inside list-disc text-sm">
        {rows.map((r) => (
          <li key={`${r.index}-${r.code}`} data-testid="rejected-row" data-code={r.code}>
            {t("rowN", { n: r.index + 1 })}: {te.has(`code.${r.code}` as "code.UNKNOWN") ? te(`code.${r.code}` as "code.UNKNOWN") : r.message}
          </li>
        ))}
      </ul>
    </Alert>
  );
}

/* ═════════════ talk detail (§3.11, §3.12, TBT-8) ═════════════ */

export function ToolboxTalkPage({ id }: { id: string }) {
  const t = useTranslations("field.talks");
  const te = useTranslations("enums");
  const tn = useTranslations("field.nav");
  const bi = useBi();
  const q = useToolboxTalk(id);
  const caps = useFieldCaps(q.data?.project_id ?? null);
  const refresh = useFieldRefresh();
  const { packs } = useFieldOffline();
  const [voiding, setVoiding] = useState(false);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const x = q.data;
  const open = x.status === "delivered";
  const namesHidden = x.attendance.length > 0 && x.attendance.every((r) => !r.name_en && !r.worker_no);
  async function remove(rowId: string) {
    setError(null);
    try {
      await unwrap(api.DELETE("/api/v1/toolbox-talks/{talk_id}/attendance/{row_id}", { params: { path: { talk_id: x.id, row_id: rowId } } }));
      await refresh();
    } catch (e) {
      setError(e);
    }
  }
  return (
    <div className="mx-auto max-w-4xl">
      <Breadcrumbs items={[{ label: tn("talks"), href: "/toolbox-talks" }, { label: x.talk_no }]} />
      <Card data-testid="talk-detail" data-status={x.status}>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
          <CardTitle className="flex flex-wrap items-center gap-2">
            <Code>{x.talk_no}</Code>
            <TalkStatusBadge status={x.status} />
            <OfflineLabel show={x.recorded_offline} minutes={x.offline_delay_min} />
          </CardTitle>
          <div className="flex flex-wrap gap-2">
            {open && caps.talk ? (
              <Button size="sm" variant="outline" onClick={() => setAdding(true)} data-testid="talk-add-rows">
                <UserPlus aria-hidden />
                {t("addRows")}
              </Button>
            ) : null}
            {x.status !== "voided" && caps.void ? (
              <Button size="sm" variant="ghost" onClick={() => setVoiding(true)} data-testid="talk-void">
                <Ban aria-hidden />
                {t("void")}
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <FieldList>
            <FieldItem label={t("delivered")}>
              <StackedDate v={x.delivered_at} time projectId={x.project_id} /> · {t("minutes", { n: x.duration_minutes })}
            </FieldItem>
            <FieldItem label={t("where")}>
              {x.site.code}
              {x.zones.length ? ` · ${x.zones.map((z) => z.code).join(", ")}` : ""}
            </FieldItem>
            <FieldItem label={t("host")}>{x.host_engagement ? <Code>{x.host_engagement.short_code}</Code> : "—"}</FieldItem>
            <FieldItem label={t("shift")}>{te(`fdShift.${x.shift}`)}</FieldItem>
            <FieldItem label={t("presenter")}>{x.presenter_name ?? "—"}</FieldItem>
            <FieldItem label={t("recordedBy")}>
              <UserName u={x.recorded_by} />
            </FieldItem>
            <FieldItem label={t("topics")} wide>
              {x.topics.map((tp, i) => (
                <span key={i} className="block">
                  {tp.topic_code ? (
                    <Link href={tp.topic_id ? `/toolbox-topics/${tp.topic_id}` : "/toolbox-topics"} className="text-primary hover:underline">
                      <Code>{tp.topic_code}</Code>
                    </Link>
                  ) : null}{" "}
                  {bi(tp.title_en, tp.title_ar)}
                </span>
              ))}
            </FieldItem>
            <FieldItem label={t("language")}>
              {te(`fdLanguage.${x.language}`)}
              {x.interpreter_languages.length ? ` + ${x.interpreter_languages.map((l) => te(`fdLanguage.${l}`)).join(", ")}` : ""}
            </FieldItem>
            <FieldItem label={t("campaign")}>{x.campaign_no ? <Code>{x.campaign_no}</Code> : "—"}</FieldItem>
            <FieldItem label={t("attendance")}>{t("counts", { named: x.named_count, briefed: x.briefed_count, unnamed: x.unnamed_count })}</FieldItem>
            <FieldItem label={t("locksAt")}>
              <StackedDate v={x.locks_at} time />
            </FieldItem>
            {x.questions_raised ? (
              <FieldItem label={t("questions")} wide>
                <span dir="auto">{x.questions_raised}</span>
              </FieldItem>
            ) : null}
            {x.status_reason ? (
              <FieldItem label={t("voidReason")} wide>
                <span dir="auto">{x.status_reason}</span>
              </FieldItem>
            ) : null}
          </FieldList>
          <RejectedRows rows={x.rejected_rows} />
          <ApiWarnings warnings={x.warnings} />
        </CardContent>
      </Card>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">{t("attendanceTitle")}</CardTitle>
          {namesHidden || !caps.names ? <p className="text-xs text-muted-foreground" data-testid="names-hidden">{t("namesHidden")}</p> : null}
        </CardHeader>
        <CardContent>
          <MutationError error={error} />
          {x.attendance.length ? (
            <Table data-testid="att-table">
              <THead>
                <TR>
                  <TH>{t("worker")}</TH>
                  <TH>{t("method")}</TH>
                  <TH>{t("signed")}</TH>
                  <TH>{t("understood")}</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {x.attendance.map((r) => (
                  <TR key={r.id} data-testid="att-detail-row" data-understood={r.understood_language}>
                    <TD label={t("worker")}>
                      {r.worker_no ? <Code className="me-1">{r.worker_no}</Code> : null}
                      {bi(r.name_en, r.name_ar) || "—"}
                      {r.engagement ? <span className="block text-xs text-muted-foreground">{r.engagement.short_code}</span> : null}
                    </TD>
                    <TD label={t("method")}>{te(`fdMethod.${r.method}`)}</TD>
                    <TD label={t("signed")}>{r.signed ? t("yes") : t("no")}</TD>
                    <TD label={t("understood")}>
                      <Badge tone={r.understood_language === "none" ? "warning" : r.understood_language === "interpreter" ? "info" : "success"}>{te(`fdUnderstood.${r.understood_language}`)}</Badge>
                    </TD>
                    <TD>
                      {open && caps.talk ? (
                        <Button size="sm" variant="ghost" onClick={() => void remove(r.id)} aria-label={t("removeRow")} data-testid="att-remove">
                          <Trash2 aria-hidden />
                        </Button>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noNamed")}</p>
          )}
          {x.sheet_photo_ids.length && caps.names ? (
            <div className="mt-4">
              <p className="mb-1 text-sm font-medium">{t("sheetPhotos")}</p>
              <Attachments ownerType="toolbox_sheet" ownerId={x.id} canUpload={false} />
            </div>
          ) : null}
        </CardContent>
      </Card>
      {adding ? <AddRowsDialog talk={x} deployments={packs[x.project_id]?.pack.deployments ?? []} onClose={() => setAdding(false)} /> : null}
      {voiding ? (
        <FieldReasonDialog
          title={t("void")}
          description={t("voidHint")}
          confirmLabel={t("void")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/toolbox-talks/{talk_id}/void", { params: { path: { talk_id: x.id } }, body: { reason } }))}
          onClose={() => setVoiding(false)}
        />
      ) : null}
    </div>
  );
}

function AddRowsDialog({ talk, deployments, onClose }: { talk: S["TalkRead"]; deployments: Dep[]; onClose: () => void }) {
  const t = useTranslations("field.talks");
  const refresh = useFieldRefresh();
  const [rows, setRows] = useState<Row[]>([]);
  const [result, setResult] = useState<S["TalkRead"] | null>(null);
  return (
    <StepDialog
      wide
      title={t("addRows")}
      description={talk.talk_no}
      confirmLabel={t("add")}
      disabled={!rows.length}
      testId="add-rows-confirm"
      onConfirm={async () => {
        const r = await unwrap(
          api.POST("/api/v1/toolbox-talks/{talk_id}/attendance", {
            params: { path: { talk_id: talk.id } },
            body: { rows: rows.map((x) => (x.method === "card_scan" ? { method: "card_scan" as const, scanned_token: x.token ?? null, signature: x.signature ?? null } : { method: "list" as const, deployment_id: x.deployment?.deployment_id ?? null, signature: x.signature ?? null })) },
          }),
        );
        setResult(r);
        await refresh();
      }}
      onClose={onClose}
    >
      <Attendance rows={rows} setRows={setRows} deployments={deployments} host={talk.host_engagement?.id ?? ""} lang={talk.language} interp={talk.interpreter_languages} />
      {result ? <RejectedRows rows={result.rejected_rows} /> : null}
    </StepDialog>
  );
}

/* ═════════════ briefing campaigns (§3.13, CMP-1…CMP-4) ═════════════ */

export function CampaignsPage() {
  return <ProjectGate>{(p) => <Campaigns project={p} />}</ProjectGate>;
}

function Campaigns({ project }: { project: Project }) {
  const t = useTranslations("field.campaigns");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useFieldCaps(project.id);
  const bi = useBi();
  const { label } = useFieldRef();
  const s = useSearchState();
  const status = (s.get("status") ?? "") as S["CampaignStatus"] | "";
  const page = Number(s.get("page") ?? 1);
  const q = useCampaigns(project.id, { status: status ? [status] : null, page, page_size: 50 }, { enabled: caps.view || caps.campaign });
  const [creating, setCreating] = useState(false);
  if (!caps.view && !caps.campaign) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.campaign ? (
            <Button onClick={() => setCreating(true)} data-testid="campaign-new">
              <Megaphone aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <FieldTalkSubNav />
      <ListToolbar>
        <SelectFilter id="cm-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={CAMPAIGN_STATUSES.map((x) => ({ value: x, label: te(`fdCampaignStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data?.items.length ? (
        <>
          <Table data-testid="campaigns-table">
            <THead>
              <TR>
                <TH>{t("campaign")}</TH>
                <TH>{t("topic")}</TH>
                <TH>{t("reason")}</TH>
                <TH>{t("due")}</TH>
                <TH className="text-end">{t("pairs")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {q.data.items.map((c) => (
                <TR key={c.id} data-testid="campaign-row" data-no={c.campaign_no} data-status={c.status}>
                  <TD label={t("campaign")}>
                    <Link href={`/briefing-campaigns/${c.id}`} className="font-medium text-primary hover:underline">
                      <Code>{c.campaign_no}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">{c.sites.map((x) => x.code).join(" · ")}</span>
                  </TD>
                  <TD label={t("topic")}>
                    <Code>{c.topic_code}</Code> {bi(c.topic_title_en, c.topic_title_ar)}
                  </TD>
                  <TD label={t("reason")}>
                    {label("campaign_reasons", c.reason)}
                    {c.reason_ref ? <Code className="ms-1 text-xs">{c.reason_ref}</Code> : null}
                  </TD>
                  <TD label={t("due")}>
                    <StackedDate v={c.due_date} />
                  </TD>
                  <TD label={t("pairs")} className="text-end tabular-nums">
                    <span data-testid="campaign-met">{t("metOf", { met: c.met_count, n: c.pairs.length })}</span>
                  </TD>
                  <TD label={tc("status")}>
                    <CampaignStatusBadge status={c.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={50} total={q.data.total} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {creating ? <CampaignDialog project={project} onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function CampaignDialog({ project, c, onClose }: { project: Project; c?: S["CampaignRead"]; onClose: () => void }) {
  const t = useTranslations("field.campaigns");
  const tc = useTranslations("common");
  const bi = useBi();
  const { label, items } = useFieldRef();
  const opts = useProjectOptions(project.id);
  const router = useRouter();
  const refresh = useFieldRefresh();
  const topics = useTopics({ status: ["published"] });
  const [topic, setTopic] = useState(c?.topic_id ?? "");
  const [reason, setReason] = useState<string>(c?.reason ?? "incident");
  const [ref, setRef] = useState(c?.reason_ref ?? "");
  const [en, setEn] = useState(c?.message_en ?? "");
  const [ar, setAr] = useState(c?.message_ar ?? "");
  const [sites, setSites] = useState<string[]>(c?.sites.map((x) => x.id) ?? []);
  const [due, setDue] = useState(c?.due_date ?? "");
  const valid = topic && sites.length && (en.trim() || ar.trim()) && (reason !== "incident" || ref.trim());
  return (
    <StepDialog
      wide
      title={c ? t("edit") : t("new")}
      description={t("newHint")}
      confirmLabel={c ? t("save") : t("createDraft")}
      disabled={!valid}
      testId="campaign-save"
      onConfirm={async () => {
        if (c) {
          await unwrap(api.PATCH("/api/v1/briefing-campaigns/{campaign_id}", { params: { path: { campaign_id: c.id } }, body: { reason_ref: ref.trim() || null, message_en: en.trim() || null, message_ar: ar.trim() || null, site_ids: sites, due_date: due || null } }));
          await refresh();
        } else {
          const r = await unwrap(
            api.POST("/api/v1/projects/{project_id}/briefing-campaigns", {
              params: { path: { project_id: project.id } },
              body: { topic_id: topic, reason: reason as S["CampaignReason"], reason_ref: ref.trim() || null, message_en: en.trim() || null, message_ar: ar.trim() || null, site_ids: sites, due_date: due || null },
            }),
          );
          await refresh();
          router.push(`/briefing-campaigns/${r.id}`);
        }
      }}
      onClose={onClose}
    >
      <FormField id="cd-topic" label={t("topic")} required hint={t("topicHint")}>
        <Select value={topic} disabled={Boolean(c)} onChange={(e) => setTopic(e.target.value)} data-testid="cd-topic">
          <option value="">—</option>
          {(topics.data?.items ?? []).map((x) => (
            <option key={x.id} value={x.id} disabled={x.review_overdue}>
              {x.topic_code} · {bi(x.title_en, x.title_ar)}
              {x.review_overdue ? ` (${t("reviewOverdue")})` : ""}
            </option>
          ))}
        </Select>
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="cd-reason" label={t("reason")} required>
          <Select value={reason} disabled={Boolean(c)} onChange={(e) => setReason(e.target.value)} data-testid="cd-reason">
            {items("campaign_reasons").map((x) => (
              <option key={x.code} value={x.code}>
                {label("campaign_reasons", x.code)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="cd-ref" label={t("reasonRef")} required={reason === "incident"} hint={reason === "incident" ? t("incidentRefHint") : undefined}>
          <Input className="ltr" maxLength={60} value={ref} onChange={(e) => setRef(e.target.value)} data-testid="cd-ref" />
        </FormField>
      </div>
      <FormField id="cd-en" label={t("messageEn")} required hint={t("noNamesMedical")}>
        <Textarea maxLength={1000} value={en} onChange={(e) => setEn(e.target.value)} data-testid="cd-message" />
      </FormField>
      <FormField id="cd-ar" label={t("messageAr")}>
        <Textarea dir="rtl" maxLength={1000} value={ar} onChange={(e) => setAr(e.target.value)} />
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2">
        <MultiSelect id="cd-sites" label={t("sites")} options={opts.sites.map((x) => ({ value: x.value, label: x.code }))} value={sites} onChange={setSites} allLabel={tc("select")} testId="cd-sites" className="lg:w-full" />
        <FormField id="cd-due" label={t("due")} hint={t("dueHint")}>
          <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        </FormField>
      </div>
    </StepDialog>
  );
}

export function CampaignPage({ id }: { id: string }) {
  const t = useTranslations("field.campaigns");
  const tn = useTranslations("field.nav");
  const bi = useBi();
  const { label } = useFieldRef();
  const q = useCampaign(id);
  const caps = useFieldCaps(q.data?.project_id ?? null);
  const refresh = useFieldRefresh();
  const [dialog, setDialog] = useState<"edit" | "issue" | "cancel" | null>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const c = q.data;
  return (
    <ProjectGate>
      {(project) => (
        <div className="mx-auto max-w-4xl">
          <Breadcrumbs items={[{ label: tn("campaigns"), href: "/briefing-campaigns" }, { label: c.campaign_no }]} />
          <Card data-testid="campaign-detail" data-status={c.status}>
            <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
              <CardTitle className="flex flex-wrap items-center gap-2">
                <Code>{c.campaign_no}</Code>
                <CampaignStatusBadge status={c.status} />
              </CardTitle>
              <div className="flex flex-wrap gap-2">
                {c.status === "draft" && caps.campaign ? (
                  <>
                    <Button size="sm" variant="outline" onClick={() => setDialog("edit")} data-testid="campaign-edit">
                      {t("edit")}
                    </Button>
                    <Button size="sm" onClick={() => setDialog("issue")} data-testid="campaign-issue">
                      <Send aria-hidden />
                      {t("issue")}
                    </Button>
                  </>
                ) : null}
                {(c.status === "draft" || c.status === "issued") && caps.campaign ? (
                  <Button size="sm" variant="ghost" onClick={() => setDialog("cancel")} data-testid="campaign-cancel">
                    <XCircle aria-hidden />
                    {t("cancel")}
                  </Button>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <FieldList>
                <FieldItem label={t("topic")}>
                  <Link href={`/toolbox-topics/${c.topic_id}`} className="text-primary hover:underline">
                    <Code>{c.topic_code}</Code> <span className="ltr">v{c.topic_version}</span>
                  </Link>{" "}
                  {bi(c.topic_title_en, c.topic_title_ar)}
                </FieldItem>
                <FieldItem label={t("reason")}>
                  {label("campaign_reasons", c.reason)} {c.reason_ref ? <Code>{c.reason_ref}</Code> : null}
                </FieldItem>
                <FieldItem label={t("sites")}>{c.sites.map((x) => x.code).join(" · ")}</FieldItem>
                <FieldItem label={t("issued")}>
                  {c.issued_at ? (
                    <>
                      <UserName u={c.issued_by} /> · <StackedDate v={c.issued_at} time />
                    </>
                  ) : (
                    "—"
                  )}
                </FieldItem>
                <FieldItem label={t("due")}>
                  <StackedDate v={c.due_date} />
                </FieldItem>
                <FieldItem label={t("message")} wide>
                  <span dir="auto" className="whitespace-pre-line">{bi(c.message_en, c.message_ar)}</span>
                </FieldItem>
                {c.status_reason ? (
                  <FieldItem label={t("cancelReason")} wide>
                    <span dir="auto">{c.status_reason}</span>
                  </FieldItem>
                ) : null}
              </FieldList>
              <ApiWarnings warnings={c.warnings} />
            </CardContent>
          </Card>
          <Card className="mt-6">
            <CardHeader>
              <CardTitle className="text-base">
                {t("pairsTitle")} · <span data-testid="campaign-met">{t("metOf", { met: c.met_count, n: c.pairs.length })}</span>
              </CardTitle>
              <p className="text-xs text-muted-foreground">{t("pairsHint")}</p>
            </CardHeader>
            <CardContent>
              {c.pairs.length ? (
                <Table data-testid="pairs-table">
                  <THead>
                    <TR>
                      <TH>{t("contractor")}</TH>
                      <TH>{t("site")}</TH>
                      <TH>{t("met")}</TH>
                      <TH>{t("talk")}</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {c.pairs.map((p, i) => (
                      <TR key={`${p.engagement?.id}-${p.site.id}-${i}`} data-testid="pair-row" data-met={p.met ? "yes" : "no"} data-on-time={p.on_time === null ? "" : p.on_time ? "yes" : "no"}>
                        <TD label={t("contractor")}>{p.engagement ? <Code>{p.engagement.short_code}</Code> : "—"}</TD>
                        <TD label={t("site")}>{p.site.code}</TD>
                        <TD label={t("met")}>
                          {p.met ? (
                            <span className="inline-flex flex-col items-start gap-1">
                              <Badge tone={p.on_time ? "success" : "warning"}>
                                <CheckCircle2 aria-hidden />
                                {p.on_time ? t("metOnTime") : t("metLate")}
                              </Badge>
                              <StackedDate v={p.met_on} />
                            </span>
                          ) : (
                            <Badge tone="danger">
                              <XCircle aria-hidden />
                              {t("notMet")}
                            </Badge>
                          )}
                        </TD>
                        <TD label={t("talk")}>{p.talk_no ? <Code>{p.talk_no}</Code> : "—"}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground">{c.status === "draft" ? t("pairsAtIssue") : t("noPairs")}</p>
              )}
            </CardContent>
          </Card>
          {dialog === "edit" ? <CampaignDialog project={project} c={c} onClose={() => setDialog(null)} /> : null}
          {dialog === "issue" ? (
            <StepDialog
              title={t("issue")}
              description={t("issueHint")}
              confirmLabel={t("issue")}
              testId="campaign-issue-confirm"
              onConfirm={async () => {
                await unwrap(api.POST("/api/v1/briefing-campaigns/{campaign_id}/transitions", { params: { path: { campaign_id: c.id } }, body: { action: "issue" } }));
                await refresh();
                toast.success(t("issuedToast"));
              }}
              onClose={() => setDialog(null)}
            />
          ) : null}
          {dialog === "cancel" ? (
            <FieldReasonDialog
              title={t("cancel")}
              confirmLabel={t("cancel")}
              min={10}
              onConfirm={(reason) => unwrap(api.POST("/api/v1/briefing-campaigns/{campaign_id}/transitions", { params: { path: { campaign_id: c.id } }, body: { action: "cancel", reason } }))}
              onClose={() => setDialog(null)}
            />
          ) : null}
        </div>
      )}
    </ProjectGate>
  );
}
