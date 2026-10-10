"use client";
import { Camera, CheckCircle2, ClipboardCheck, Plus, QrCode, ScanLine, Star, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Code, QrImage, StepDialog } from "@/components/access/common";
import { TpiSelect, Tick, UserName } from "@/components/cert/common";
import { CameraScanner } from "@/components/gate/gate-check";
import { StackedDate } from "@/components/medical/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAssetChecks, useEmergencyAsset, useEmergencyAssets, useEmergencyRefresh } from "@/lib/api/emergency";
import { ASSET_STATUSES, CHECK_ANSWERS, EXPIRY_ITEMS, EXTINGUISHER_SUBTYPES, NOT_READY } from "@/lib/emergency-enums";
import { useSearchState } from "@/lib/url-state";
import { AnswerButtons, AssetStatusBadge, EmAssetSubNav, EmReasonDialog, fromLocalInput, nowLocal, ReadyBadge, useEmCaps, useEmRef } from "./common";
import { RegistryExport } from "@/components/scorecard/exports";

type S = Schemas;
type Project = S["ProjectRead"];
type Asset = S["AssetRead"];

/* ═════════════ emergency equipment register (§3.8, EA-1, EA-5, EA-7) ═════════════ */

export function EmergencyAssetsPage() {
  return <ProjectGate>{(p) => <Assets project={p} />}</ProjectGate>;
}

function Assets({ project }: { project: Project }) {
  const t = useTranslations("emergency.assets");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { label, items: refItems } = useEmRef();
  const s = useSearchState();
  const site = s.get("site") ?? "";
  const type = s.get("type") ?? "";
  const status = (s.get("status") ?? "") as S["AssetStatus"] | "";
  const reason = (s.get("reason") ?? "") as S["NotReadyReason"] | "";
  const ready = s.get("ready") ?? "";
  const page = Number(s.get("page") ?? 1);
  const q = useEmergencyAssets(
    project.id,
    { site_id: site || null, asset_type: type ? [type as S["app__core__emergency_enums__AssetType"]] : null, status: status || null, not_ready_reason: reason || null, ready: ready ? ready === "yes" : null, page, page_size: 50 },
    { enabled: caps.view },
  );
  const [edit, setEdit] = useState<Asset | "new" | null>(null);
  const [qr, setQr] = useState<Asset | null>(null);
  const [move, setMove] = useState<{ a: Asset; action: S["AssetAction"] } | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <div className="flex flex-wrap gap-2">
            {caps.check ? (
              <Button asChild variant="outline">
                <Link href="/emergency-asset-checks/new" data-testid="asset-check-new">
                  <ClipboardCheck aria-hidden />
                  {t("recordCheck")}
                </Link>
              </Button>
            ) : null}
            {caps.assets ? (
              <Button onClick={() => setEdit("new")} data-testid="asset-new">
                <Plus aria-hidden />
                {t("new")}
              </Button>
            ) : null}
          </div>
        }
      />
      <EmAssetSubNav />
      <ListToolbar actions={<RegistryExport dataset="emergency_assets" projectId={project.id} />}>
        <SelectFilter id="as-site" label={t("site")} value={site} onChange={(v) => s.set({ site: v, page: null })} options={opts.sites.map((x) => ({ value: x.value, label: x.code }))} />
        <SelectFilter id="as-type" label={t("type")} value={type} onChange={(v) => s.set({ type: v, page: null })} options={refItems("asset_types").map((x) => ({ value: x.code, label: label("asset_types", x.code) }))} />
        <SelectFilter id="as-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={ASSET_STATUSES.map((x) => ({ value: x, label: te(`emAssetStatus.${x}`) }))} />
        <SelectFilter id="as-ready" label={t("ready")} value={ready as "yes" | "no" | ""} onChange={(v) => s.set({ ready: v, page: null })} options={[{ value: "yes", label: t("readyYes") }, { value: "no", label: t("readyNo") }]} />
        <SelectFilter id="as-reason" label={t("reason")} value={reason} onChange={(v) => s.set({ reason: v, page: null })} options={NOT_READY.map((x) => ({ value: x, label: te(`emNotReady.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="assets-table">
            <THead>
              <TR>
                <TH>{t("tag")}</TH>
                <TH>{t("type")}</TH>
                <TH>{t("where")}</TH>
                <TH>{t("lastCheck")}</TH>
                <TH>{t("readiness")}</TH>
                <TH>{tc("status")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="asset-row" data-tag={a.asset_tag} data-status={a.status} data-ready={a.readiness.ready ? "yes" : "no"}>
                  <TD label={t("tag")}>
                    <Code className="font-medium">{a.asset_tag}</Code>
                    {a.owner_code ? <span className="block text-xs text-muted-foreground">{a.owner_code}</span> : null}
                  </TD>
                  <TD label={t("type")}>
                    {label("asset_types", a.asset_type)}
                    {a.subtype || a.capacity ? (
                      <span className="block text-xs text-muted-foreground">
                        {a.subtype ? te.has(`emSubtype.${a.subtype}` as never) ? te(`emSubtype.${a.subtype}` as never) : a.subtype : null}
                        {a.capacity ? <> · <bdi className="ltr">{a.capacity}</bdi></> : null}
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("where")}>
                    <Code>{a.site_code}</Code>
                    {a.zone_code ? (
                      <>
                        {" · "}
                        <Code>{a.zone_code}</Code>
                      </>
                    ) : null}
                    <span dir="auto" className="block text-xs text-muted-foreground">
                      {a.location_en}
                    </span>
                  </TD>
                  <TD label={t("lastCheck")}>
                    <StackedDate v={a.last_check_at} projectId={project.id} />
                    {a.last_check_result ? <CheckResultBadge result={a.last_check_result} /> : null}
                    {a.flagged_without_scan ? (
                      <Badge tone="warning" className="mt-1" data-testid="flag-no-scan">
                        {t("noScan")}
                      </Badge>
                    ) : null}
                  </TD>
                  <TD label={t("readiness")}>
                    <ReadyBadge ready={a.readiness.ready} reasons={a.readiness.reasons} />
                    {a.readiness.check_due_on ? (
                      <span className="block text-xs text-muted-foreground">
                        {t("checkDue")} <StackedDate v={a.readiness.check_due_on} projectId={project.id} />
                      </span>
                    ) : null}
                  </TD>
                  <TD label={tc("status")}>
                    <AssetStatusBadge status={a.status} />
                  </TD>
                  <TD>
                    <span className="flex flex-wrap gap-1">
                      {caps.check && a.status !== "retired" ? (
                        <Button size="sm" asChild>
                          <Link href={`/emergency-asset-checks/new?asset=${a.id}`} data-testid="asset-check">
                            {t("check")}
                          </Link>
                        </Button>
                      ) : null}
                      <Button size="sm" variant="outline" asChild>
                        <Link href={`/emergency-asset-checks?asset=${a.id}`} data-testid="asset-history">
                          {t("history")}
                        </Link>
                      </Button>
                      {a.sticker_payload ? (
                        <Button size="sm" variant="outline" onClick={() => setQr(a)} aria-label={t("sticker")} data-testid="asset-qr">
                          <QrCode aria-hidden />
                        </Button>
                      ) : null}
                      {caps.assets && a.status !== "retired" ? (
                        <Button size="sm" variant="outline" onClick={() => setEdit(a)} data-testid="asset-edit">
                          {t("edit")}
                        </Button>
                      ) : null}
                      {caps.check && a.status === "in_service" ? (
                        <Button size="sm" variant="destructive-outline" onClick={() => setMove({ a, action: "tag_out" })} data-testid="asset-tag-out">
                          {t("tagOut")}
                        </Button>
                      ) : null}
                      {caps.assets && a.status !== "retired" ? (
                        <Button size="sm" variant="destructive-outline" onClick={() => setMove({ a, action: "retire" })} data-testid="asset-retire">
                          {t("retire")}
                        </Button>
                      ) : null}
                    </span>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={50} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: String(p) })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {edit ? <AssetDialog project={project} a={edit === "new" ? null : edit} onClose={() => setEdit(null)} /> : null}
      {qr?.sticker_payload ? (
        <StepDialog title={t("stickerTitle", { tag: qr.asset_tag })} description={t("stickerHint")} confirmLabel={t("print")} onConfirm={async () => window.print()} onClose={() => setQr(null)}>
          <div className="flex flex-col items-center gap-2" data-testid="asset-sticker">
            <QrImage payload={qr.sticker_payload} size={200} label={qr.asset_tag} />
            <Code className="text-lg font-semibold">{qr.asset_tag}</Code>
          </div>
        </StepDialog>
      ) : null}
      {move ? (
        <EmReasonDialog
          title={t(move.action === "retire" ? "retireTitle" : "tagOutTitle", { tag: move.a.asset_tag })}
          description={move.action === "retire" ? t("retireHint") : t("tagOutHint")}
          confirmLabel={t(move.action === "retire" ? "retire" : "tagOut")}
          min={5}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/emergency-assets/{asset_id}/transitions", { params: { path: { asset_id: move.a.id } }, body: { action: move.action, reason } }))}
          onClose={() => setMove(null)}
        />
      ) : null}
    </div>
  );
}

function CheckResultBadge({ result }: { result: S["CheckResult"] }) {
  const te = useTranslations("enums");
  return (
    <Badge tone={result === "pass" ? "success" : "danger"} className="mt-1" data-testid="check-result" data-result={result}>
      {result === "pass" ? <CheckCircle2 aria-hidden /> : <XCircle aria-hidden />}
      {te(`emCheckResult.${result}`)}
    </Badge>
  );
}

function AssetDialog({ project, a, onClose }: { project: Project; a: Asset | null; onClose: () => void }) {
  const t = useTranslations("emergency.assets");
  const te = useTranslations("enums");
  const { label, items } = useEmRef();
  const opts = useProjectOptions(project.id);
  const refresh = useEmergencyRefresh();
  const [tag, setTag] = useState(a?.asset_tag ?? "");
  const [type, setType] = useState<string>(a?.asset_type ?? "fire_extinguisher");
  const [subtype, setSubtype] = useState(a?.subtype ?? "dcp_abc");
  const [capacity, setCapacity] = useState(a?.capacity ?? "");
  const [site, setSite] = useState(a?.site_id ?? "");
  const [zone, setZone] = useState(a?.zone_id ?? "");
  const [loc, setLoc] = useState(a?.location_en ?? "");
  const [owner, setOwner] = useState(a?.owner_engagement_id ?? "");
  const [year, setYear] = useState(a?.manufactured_year ? String(a.manufactured_year) : "");
  const [serial, setSerial] = useState(a?.serial_no ?? "");
  const [service, setService] = useState(a?.last_service_on ?? "");
  const [provider, setProvider] = useState(a?.service_provider_tpi_id ?? "");
  const [serviceRef, setServiceRef] = useState(a?.service_ref ?? "");
  const [expiries, setExpiries] = useState<S["ExpiryInput"][]>((a?.expiries ?? []).map((x) => ({ item: x.item as S["ExpiryItem"], expires_on: String(x.expires_on) })));
  const ext = type === "fire_extinguisher";
  return (
    <StepDialog
      wide
      title={a ? t("editTitle", { tag: a.asset_tag }) : t("new")}
      description={t("newHint")}
      confirmLabel={t("save")}
      disabled={!tag || !site || !loc || !owner}
      testId="asset-save"
      onConfirm={async () => {
        const svc = { last_service_on: service || null, service_provider_tpi_id: provider || null, service_ref: serviceRef || null, expiries };
        if (a) {
          await unwrap(api.PATCH("/api/v1/emergency-assets/{asset_id}", { params: { path: { asset_id: a.id } }, body: { zone_id: zone || null, location_en: loc, capacity: capacity || null, ...svc } }));
        } else {
          const r = await unwrap(
            api.POST("/api/v1/projects/{project_id}/emergency-assets", {
              params: { path: { project_id: project.id } },
              body: {
                asset_tag: tag.trim(),
                asset_type: type as S["app__core__emergency_enums__AssetType"],
                subtype: ext ? subtype : null,
                capacity: capacity || null,
                site_id: site,
                zone_id: zone || null,
                location_en: loc,
                owner_engagement_id: owner,
                manufactured_year: year ? Number(year) : null,
                serial_no: serial || null,
                ...svc,
              },
            }),
          );
          toast.success(t("registered", { tag: r.asset_tag }));
        }
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ea-tag" label={t("tag")} required hint={t("tagHint")}>
          <Input className="ltr" disabled={Boolean(a)} value={tag} onChange={(x) => setTag(x.target.value.toUpperCase())} maxLength={20} data-testid="ea-tag" />
        </FormField>
        <FormField id="ea-type" label={t("type")} required>
          <Select disabled={Boolean(a)} value={type} onChange={(x) => setType(x.target.value)} data-testid="ea-type">
            {items("asset_types").map((x) => (
              <option key={x.code} value={x.code}>
                {label("asset_types", x.code)}
              </option>
            ))}
          </Select>
        </FormField>
        {ext && !a ? (
          <FormField id="ea-subtype" label={t("subtype")} required>
            <Select value={subtype} onChange={(x) => setSubtype(x.target.value)}>
              {EXTINGUISHER_SUBTYPES.map((x) => (
                <option key={x} value={x}>
                  {te(`emSubtype.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <FormField id="ea-capacity" label={t("capacity")}>
          <Input value={capacity} onChange={(x) => setCapacity(x.target.value)} maxLength={20} placeholder="6 kg" />
        </FormField>
        <FormField id="ea-site" label={t("site")} required>
          <Select disabled={Boolean(a)} value={site} onChange={(x) => (setSite(x.target.value), setZone(""))} data-testid="ea-site">
            <option value="">—</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ea-zone" label={t("zone")}>
          <Select value={zone} onChange={(x) => setZone(x.target.value)} data-testid="ea-zone">
            <option value="">—</option>
            {opts.zones
              .filter((z) => z.siteId === site)
              .map((z) => (
                <option key={z.value} value={z.value}>
                  {z.label}
                </option>
              ))}
          </Select>
        </FormField>
        <FormField id="ea-loc" label={t("location")} required className="sm:col-span-2">
          <Input value={loc} onChange={(x) => setLoc(x.target.value)} maxLength={200} data-testid="ea-loc" />
        </FormField>
        <FormField id="ea-owner" label={t("owner")} required>
          <Select disabled={Boolean(a)} value={owner} onChange={(x) => setOwner(x.target.value)} data-testid="ea-owner">
            <option value="">—</option>
            {opts.engagements.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        {!a ? (
          <>
            <FormField id="ea-year" label={t("year")} hint={ext ? t("yearHint") : undefined}>
              <Input type="number" min={1990} max={2100} value={year} onChange={(x) => setYear(x.target.value)} data-testid="ea-year" />
            </FormField>
            <FormField id="ea-serial" label={t("serial")}>
              <Input className="ltr" value={serial} onChange={(x) => setSerial(x.target.value)} maxLength={40} />
            </FormField>
          </>
        ) : null}
        <FormField id="ea-service" label={t("lastService")} hint={t("serviceHint")}>
          <Input type="date" value={service} onChange={(x) => setService(x.target.value)} data-testid="ea-service" />
        </FormField>
        <TpiSelect id="ea-provider" label={t("provider")} kind="fire_protection_service" value={provider} onChange={(id) => setProvider(id)} />
        <FormField id="ea-service-ref" label={t("serviceRef")}>
          <Input className="ltr" value={serviceRef} onChange={(x) => setServiceRef(x.target.value)} maxLength={40} />
        </FormField>
      </div>
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">{t("expiries")}</p>
        {expiries.map((x, i) => (
          <div key={i} className="flex flex-wrap items-end gap-2">
            <Select aria-label={t("expiryItem")} value={x.item} onChange={(e) => setExpiries(expiries.map((y, j) => (j === i ? { ...y, item: e.target.value as S["ExpiryItem"] } : y)))} className="w-44">
              {EXPIRY_ITEMS.map((k) => (
                <option key={k} value={k}>
                  {te(`emExpiry.${k}`)}
                </option>
              ))}
            </Select>
            <Input type="date" aria-label={t("expiresOn")} value={x.expires_on} onChange={(e) => setExpiries(expiries.map((y, j) => (j === i ? { ...y, expires_on: e.target.value } : y)))} className="w-44" />
            <Button size="sm" variant="ghost" onClick={() => setExpiries(expiries.filter((_, j) => j !== i))}>
              {t("remove")}
            </Button>
          </div>
        ))}
        <Button size="sm" variant="outline" className="w-fit" onClick={() => setExpiries([...expiries, { item: "pads", expires_on: "" }])}>
          <Plus aria-hidden />
          {t("addExpiry")}
        </Button>
      </div>
    </StepDialog>
  );
}

/* ═════════════ asset checks (§3.9, EA-2…EA-4) ═════════════ */

export function AssetChecksPage() {
  return <ProjectGate>{(p) => <Checks project={p} />}</ProjectGate>;
}

function Checks({ project }: { project: Project }) {
  const t = useTranslations("emergency.checks");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const s = useSearchState();
  const asset = s.get("asset") ?? "";
  const page = Number(s.get("page") ?? 1);
  const q = useAssetChecks(project.id, { asset_id: asset || null, page, page_size: 50 }, { enabled: caps.view });
  const a = useEmergencyAsset(asset, { enabled: Boolean(asset) });
  const [voiding, setVoiding] = useState<S["CheckRead"] | null>(null);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={asset && a.data ? t("titleFor", { tag: a.data.asset_tag }) : t("title")}
        description={t("subtitle")}
        actions={
          caps.check ? (
            <Button asChild>
              <Link href={asset ? `/emergency-asset-checks/new?asset=${asset}` : "/emergency-asset-checks/new"} data-testid="check-new">
                <ClipboardCheck aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <EmAssetSubNav />
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
                <TH>{t("asset")}</TH>
                <TH>{t("at")}</TH>
                <TH>{t("by")}</TH>
                <TH>{t("method")}</TH>
                <TH>{t("result")}</TH>
                <TH>{t("ca")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((c) => (
                <TR key={c.id} data-testid="check-row" data-no={c.check_no} data-result={c.result} data-status={c.status}>
                  <TD label={t("no")}>
                    <Code className="text-xs">{c.check_no}</Code>
                  </TD>
                  <TD label={t("asset")}>
                    <Code>{c.asset_tag}</Code>
                  </TD>
                  <TD label={t("at")}>
                    <StackedDate v={c.checked_at} time projectId={project.id} />
                  </TD>
                  <TD label={t("by")}>
                    <UserName u={c.checked_by} />
                  </TD>
                  <TD label={t("method")}>
                    {te(`emCheckMethod.${c.method}`)}
                    {c.outcome === "missing" ? <Badge tone="danger" className="ms-1">{te("emCheckOutcome.missing")}</Badge> : null}
                  </TD>
                  <TD label={t("result")}>
                    {c.status === "voided" ? <Badge tone="neutral">{te("emRecordStatus.voided")}</Badge> : <CheckResultBadge result={c.result} />}
                    {c.fixed_on_spot ? <span className="block text-xs text-muted-foreground">{t("fixedOnSpot")}</span> : null}
                  </TD>
                  <TD label={t("ca")}>{c.ca_ref ? <Code>{c.ca_ref}</Code> : "—"}</TD>
                  <TD>
                    {caps.void && c.status === "valid" ? (
                      <Button size="sm" variant="destructive-outline" onClick={() => setVoiding(c)} data-testid="check-void">
                        {t("void")}
                      </Button>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={50} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: String(p) })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {voiding ? (
        <EmReasonDialog
          title={t("voidTitle", { no: voiding.check_no })}
          confirmLabel={t("void")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/emergency-asset-checks/{check_id}/void", { params: { path: { check_id: voiding.id } }, body: { reason } }))}
          onClose={() => setVoiding(null)}
        />
      ) : null}
    </div>
  );
}

/* ═════════════ phone-first check entry (scan the EA sticker or choose the asset) ═════════════ */

export function AssetCheckEntryPage() {
  return <ProjectGate>{(p) => <CheckEntry project={p} />}</ProjectGate>;
}

function CheckEntry({ project }: { project: Project }) {
  const t = useTranslations("emergency.entry");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const s = useSearchState();
  const preset = s.get("asset") ?? "";
  const [assetId, setAssetId] = useState(preset);
  const [payload, setPayload] = useState("");
  const [saved, setSaved] = useState<S["CheckRead"] | null>(null);
  const [key, setKey] = useState(0);
  if (!caps.check) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title={t("title")} description={t("subtitle")} />
      {saved ? (
        <Saved
          c={saved}
          onAgain={() => {
            setSaved(null);
            setAssetId("");
            setPayload("");
            setKey(key + 1);
          }}
        />
      ) : (
        <CheckForm key={key} project={project} assetId={assetId} setAssetId={setAssetId} payload={payload} setPayload={setPayload} onSaved={setSaved} />
      )}
    </div>
  );
}

function CheckForm({
  project,
  assetId,
  setAssetId,
  payload,
  setPayload,
  onSaved,
}: {
  project: Project;
  assetId: string;
  setAssetId: (v: string) => void;
  payload: string;
  setPayload: (v: string) => void;
  onSaved: (c: S["CheckRead"]) => void;
}) {
  const t = useTranslations("emergency.entry");
  const te = useTranslations("enums");
  const { items, label } = useEmRef();
  const opts = useProjectOptions(project.id);
  const refresh = useEmergencyRefresh();
  const [camera, setCamera] = useState(false);
  const [site, setSite] = useState("");
  const [zone, setZone] = useState("");
  const [type, setType] = useState("");
  const [typed, setTyped] = useState("");
  const pick = useEmergencyAssets(project.id, { site_id: site || null, zone_id: zone || null, asset_type: type ? [type as S["app__core__emergency_enums__AssetType"]] : null, page_size: 200 }, { enabled: Boolean(site) && !assetId && !payload });
  const asset = useEmergencyAsset(assetId, { enabled: Boolean(assetId) });
  const [outcome, setOutcome] = useState<S["CheckOutcome"]>("checked");
  const [answers, setAnswers] = useState<Record<string, S["CheckAnswer"]>>({});
  const [fixed, setFixed] = useState(false);
  const [late, setLate] = useState(false);
  const [at, setAt] = useState(nowLocal());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const a = asset.data;
  const scanned = Boolean(payload);
  // The items applicable to the type (EC list `applies_to`); a scanned sticker shows them once the type is chosen below.
  const [scanType, setScanType] = useState("");
  const assetType = a?.asset_type ?? scanType;
  const ecs = items("check_items").filter((c) => !assetType || (c.applies_to ?? []).includes(assetType));
  const critFail = ecs.some((c) => c.critical && answers[c.code] === "fail");
  const nonCritFail = ecs.some((c) => !c.critical && answers[c.code] === "fail");
  const complete = outcome === "missing" || (Boolean(assetType) && ecs.every((c) => answers[c.code]));
  const identified = Boolean(a) || scanned;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const c = await unwrap(
        api.POST("/api/v1/projects/{project_id}/emergency-asset-checks", {
          params: { path: { project_id: project.id } },
          body: {
            asset_id: scanned ? null : assetId,
            sticker_payload: scanned ? payload.trim() : null,
            checked_at: late ? fromLocalInput(at) : null,
            outcome,
            items: outcome === "checked" ? ecs.map((c) => ({ item: c.code as S["CheckItem"], answer: answers[c.code] as S["CheckAnswer"] })) : [],
            fixed_on_spot: fixed && nonCritFail && !critFail,
          },
        }),
      );
      await refresh();
      onSaved(c);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4" data-testid="check-entry">
      {!identified ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("identify")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Button className="min-h-12 text-base" onClick={() => setCamera(true)} data-testid="ce-camera">
              <Camera aria-hidden />
              {t("scan")}
            </Button>
            {camera ? <CameraScanner onResult={(p) => (setPayload(p), setCamera(false))} onClose={() => setCamera(false)} paused={false} /> : null}
            <div className="flex gap-2">
              <Input className="ltr" placeholder="HSE2:EA:…" value={typed} onChange={(x) => setTyped(x.target.value)} aria-label={t("payload")} data-testid="ce-payload" />
              <Button variant="outline" disabled={!typed.trim()} onClick={() => setPayload(typed.trim())} data-testid="ce-payload-go">
                <ScanLine aria-hidden />
                {t("use")}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">{t("orChoose")}</p>
            <div className="grid gap-3 sm:grid-cols-3">
              <FormField id="ce-site" label={t("site")}>
                <Select value={site} onChange={(x) => (setSite(x.target.value), setZone(""))} data-testid="ce-site">
                  <option value="">—</option>
                  {opts.sites.map((x) => (
                    <option key={x.value} value={x.value}>
                      {x.code}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="ce-zone" label={t("zone")}>
                <Select value={zone} onChange={(x) => setZone(x.target.value)} data-testid="ce-zone">
                  <option value="">—</option>
                  {opts.zones
                    .filter((z) => z.siteId === site)
                    .map((z) => (
                      <option key={z.value} value={z.value}>
                        {z.label}
                      </option>
                    ))}
                </Select>
              </FormField>
              <FormField id="ce-type" label={t("type")}>
                <Select value={type} onChange={(x) => setType(x.target.value)} data-testid="ce-type">
                  <option value="">—</option>
                  {items("asset_types").map((x) => (
                    <option key={x.code} value={x.code}>
                      {label("asset_types", x.code)}
                    </option>
                  ))}
                </Select>
              </FormField>
            </div>
            {site ? (
              <FormField id="ce-asset" label={t("asset")} hint={t("manualHint")}>
                <Select value="" onChange={(x) => setAssetId(x.target.value)} data-testid="ce-asset">
                  <option value="">—</option>
                  {(pick.data?.items ?? [])
                    .filter((x) => x.status !== "retired")
                    .map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.asset_tag} · {label("asset_types", x.asset_type)}
                      </option>
                    ))}
                </Select>
              </FormField>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <Card data-testid="ce-asset-card">
          <CardContent className="flex flex-wrap items-center gap-3 p-4">
            {a ? (
              <>
                <Code className="text-lg font-semibold" data-testid="ce-tag">
                  {a.asset_tag}
                </Code>
                <span>{label("asset_types", a.asset_type)}</span>
                <span className="text-sm text-muted-foreground">
                  {a.site_code}
                  {a.zone_code ? ` · ${a.zone_code}` : ""} · <span dir="auto">{a.location_en}</span>
                </span>
                <AssetStatusBadge status={a.status} />
              </>
            ) : (
              <>
                <Badge tone="info">
                  <ScanLine aria-hidden />
                  {t("scanned")}
                </Badge>
                <Code className="text-xs">{payload}</Code>
                <FormField id="ce-scan-type" label={t("scanType")} hint={t("scanTypeHint")}>
                  <Select value={scanType} onChange={(x) => setScanType(x.target.value)} data-testid="ce-scan-type">
                    <option value="">—</option>
                    {items("asset_types").map((x) => (
                      <option key={x.code} value={x.code}>
                        {label("asset_types", x.code)}
                      </option>
                    ))}
                  </Select>
                </FormField>
              </>
            )}
            <Button variant="ghost" size="sm" className="ms-auto" onClick={() => (setAssetId(""), setPayload(""), setAnswers({}))} data-testid="ce-change">
              {t("change")}
            </Button>
          </CardContent>
        </Card>
      )}
      {identified ? (
        <>
          {!scanned ? (
            <Alert tone="info" data-testid="ce-manual-note">
              {t("manualNote")}
            </Alert>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("outcome")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <AnswerButtons
                value={outcome}
                options={[
                  { value: "checked" as const, label: te("emCheckOutcome.checked") },
                  { value: "missing" as const, label: te("emCheckOutcome.missing") },
                ]}
                onChange={setOutcome}
                danger={["missing"]}
                testId="ce-outcome"
              />
              {outcome === "checked" ? (
                <ol className="flex flex-col gap-3" data-testid="ce-items">
                  {ecs.map((c) => (
                    <li key={c.code} className="flex flex-col gap-2 rounded-md border p-3" data-testid="ce-item" data-code={c.code}>
                      <span className="flex items-start gap-2 text-sm">
                        <Code className="font-semibold">{c.code}</Code>
                        <span className="flex-1">{label("check_items", c.code)}</span>
                        {c.critical ? (
                          <Badge tone="danger" className="shrink-0">
                            <Star aria-hidden />
                            {t("critical")}
                          </Badge>
                        ) : null}
                      </span>
                      <AnswerButtons value={answers[c.code]} options={CHECK_ANSWERS.map((x) => ({ value: x, label: te(`checkAnswer.${x}`) }))} onChange={(v) => setAnswers({ ...answers, [c.code]: v })} danger={["fail"]} testId={`ce-${c.code}`} />
                    </li>
                  ))}
                </ol>
              ) : (
                <Alert tone="danger">{t("missingNote")}</Alert>
              )}
              {outcome === "checked" && nonCritFail && !critFail ? <Tick id="ce-fixed" label={t("fixedOnSpot")} checked={fixed} onChange={setFixed} /> : null}
              {critFail || outcome === "missing" ? (
                <Alert tone="danger" data-testid="ce-fail-note">
                  {t("failNote")}
                </Alert>
              ) : null}
              <Tick id="ce-late" label={t("late")} checked={late} onChange={setLate} />
              {late ? (
                <FormField id="ce-at" label={t("checkedAt")} hint={t("lateHint")}>
                  <Input type="datetime-local" value={at} onChange={(x) => setAt(x.target.value)} />
                </FormField>
              ) : null}
            </CardContent>
          </Card>
          <MutationError error={error} />
          {!complete ? <p className="text-sm text-muted-foreground">{t("toSave")}</p> : null}
          <Button className="min-h-12 text-base" disabled={busy || !complete} onClick={() => void save()} data-testid="ce-save">
            {t("save")}
          </Button>
        </>
      ) : null}
    </div>
  );
}

function Saved({ c, onAgain }: { c: S["CheckRead"]; onAgain: () => void }) {
  const t = useTranslations("emergency.entry");
  const asset = useEmergencyAsset(c.asset_id);
  const pass = c.result === "pass";
  return (
    <div className="flex flex-col gap-4" data-testid="check-saved" data-no={c.check_no} data-result={c.result}>
      <div className={pass ? "rounded-md border-2 border-success/40 bg-success-bg p-4 text-success" : "rounded-md border-2 border-danger/50 bg-danger-bg p-4 text-danger"}>
        <p className="flex items-center gap-2 text-xl font-bold">
          {pass ? <CheckCircle2 aria-hidden className="size-7" /> : <XCircle aria-hidden className="size-7" />}
          {pass ? t("passed") : t("failed")}
        </p>
        <p className="mt-1 text-sm">
          <Code>{c.check_no}</Code> · <Code>{c.asset_tag}</Code>
        </p>
        {c.ca_ref ? (
          <p className="mt-1 text-sm" data-testid="saved-ca">
            {t("caRaised")} <Code>{c.ca_ref}</Code>
          </p>
        ) : null}
        {asset.data ? (
          <p className="mt-2 text-sm">
            {t("assetNow")} <AssetStatusBadge status={asset.data.status} />
          </p>
        ) : null}
      </div>
      <ApiWarnings warnings={c.warnings} />
      <Button className="min-h-12 text-base" onClick={onAgain} data-testid="ce-again">
        {t("again")}
      </Button>
    </div>
  );
}
