"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectGate } from "@/components/common/project-gate";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  MutationError,
} from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import {
  AREA_CATEGORIES,
  CARD_COLOURS,
  HOOK_KINDS,
  PASS_AREA_KINDS,
  TRADES,
} from "@/lib/access-enums";
import {
  ak,
  useHookProviders,
  useInductionCourses,
  usePassAreas,
  usePassCategories,
  useZoneProfiles,
} from "@/lib/api/access";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { useSearchState } from "@/lib/url-state";
import { AirportOnly, Code } from "./common";
import { WorkerSubNav } from "./workers";

type Hook = Schemas["HookRequirement"];

/** Edit a list of {kind, code} hook requirements (HK-2). */
/** Hook requirements editor. `withTrades` offers the per-trade limit (zone profiles, v0.3.1). */
export function HookEditor({
  id,
  value,
  onChange,
  withTrades = false,
}: {
  id: string;
  value: Hook[];
  onChange: (v: Hook[]) => void;
  withTrades?: boolean;
}) {
  const t = useTranslations("zoneProfiles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const [kind, setKind] = useState<Schemas["HookKind"]>("training_course");
  const [code, setCode] = useState("");
  const [trades, setTrades] = useState<Schemas["Trade"][]>([]);
  return (
    <div className="flex flex-col gap-2" data-testid={id}>
      <ul className="flex flex-wrap gap-2">
        {value.map((h, i) => (
          <li
            key={`${h.kind}-${h.code}`}
            className="flex items-center gap-1 rounded-md border bg-muted/40 px-2 py-1 text-sm"
          >
            <span>{te(`hookKind.${h.kind}`)}</span>
            <Code>{h.code}</Code>
            {h.trades?.length ? (
              <span className="text-xs text-muted-foreground">
                ({h.trades.map((x) => te(`trade.${x}`)).join(" · ")})
              </span>
            ) : null}
            <Button
              type="button"
              size="icon"
              variant="ghost"
              aria-label={tc("remove")}
              onClick={() => onChange(value.filter((_, j) => j !== i))}
            >
              <Trash2 aria-hidden className="size-4" />
            </Button>
          </li>
        ))}
        {value.length === 0 ? (
          <li className="text-sm text-muted-foreground">{t("noHooks")}</li>
        ) : null}
      </ul>
      <div className="flex flex-wrap items-end gap-2">
        <Select
          aria-label={t("hookKind")}
          value={kind}
          onChange={(e) => setKind(e.target.value as Schemas["HookKind"])}
          className="w-auto"
        >
          {HOOK_KINDS.map((k) => (
            <option key={k} value={k}>
              {te(`hookKind.${k}`)}
            </option>
          ))}
        </Select>
        <Input
          aria-label={t("hookCode")}
          placeholder={t("hookCode")}
          value={code}
          maxLength={40}
          onChange={(e) => setCode(e.target.value)}
          className="ltr w-40 uppercase"
        />
        {withTrades ? (
          <MultiSelect
            id={`${id}-trades`}
            label={t("hookTrades")}
            options={TRADES.map((x) => ({ value: x, label: te(`trade.${x}`) }))}
            value={trades}
            onChange={setTrades}
            allLabel={t("allTrades")}
          />
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!code.trim()}
          onClick={() => {
            const c = code.trim().toUpperCase();
            if (!value.some((h) => h.kind === kind && h.code === c))
              onChange([
                ...value,
                { kind, code: c, ...(trades.length ? { trades } : {}) },
              ]);
            setCode("");
            setTrades([]);
          }}
        >
          <Plus aria-hidden />
          {t("addHook")}
        </Button>
      </div>
    </div>
  );
}

/* ───────────────────────────── Zone access profiles ───────────────────────────── */

export function ZoneProfilesPage() {
  return <ProjectGate>{(p) => <ZoneProfiles project={p} />}</ProjectGate>;
}

function ZoneProfiles({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("zoneProfiles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const site = s.get("site_id") || null;
  const q = useZoneProfiles(project.id, site);
  const hooks = useHookProviders(project.id);
  const [edit, setEdit] = useState<Schemas["ZoneAccessProfileRead"] | null>(
    null,
  );
  const canEdit = canWrite(me, "zone_profile.edit", project.id);
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <WorkerSubNav />
      {hooks.data ? (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base">{t("hookProviders")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul
              className="grid gap-2 sm:grid-cols-2"
              data-testid="hook-providers"
            >
              {hooks.data.map((h) => (
                <li
                  key={h.kind}
                  className="flex flex-wrap items-center gap-2 text-sm"
                >
                  <span className="font-medium">
                    {te(`hookKind.${h.kind}`)}
                  </span>
                  {h.registered ? (
                    <StatusBadge status="active" label={t("registered")} />
                  ) : (
                    <StatusBadge
                      status="warn"
                      label={t("availableFrom", {
                        phase: h.available_from_phase,
                      })}
                    />
                  )}
                  <span className="text-muted-foreground">
                    · {te(`hookPolicy.${h.policy}`)}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
      <ListToolbar>
        <SelectFilter
          id="zp-site"
          label={tc("site")}
          value={site ?? ""}
          onChange={(v) => s.set({ site_id: v })}
          options={opts.sites.map((x) => ({ value: x.value, label: x.label }))}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="zone-profiles-table">
          <THead>
            <TR>
              <TH>{tc("zone")}</TH>
              <TH>{t("fields.required_inductions")}</TH>
              <TH>{t("fields.airport_pass_area_code")}</TH>
              <TH>{t("fields.access_permit_required")}</TH>
              <TH>{t("fields.adp_category_required")}</TH>
              <TH>{t("fields.escort_ratio_max")}</TH>
              <TH>{t("fields.hook_requirements")}</TH>
              <TH>
                <span className="sr-only">{tc("actions")}</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {items.map((p) => (
              <TR
                key={p.zone.id}
                data-testid="zone-profile-row"
                data-zone={p.zone.code}
              >
                <TD label={tc("zone")}>
                  <Code>{p.zone.code}</Code>{" "}
                  {name(p.zone.name_en, p.zone.name_ar)}
                  <span className="block text-xs text-muted-foreground">
                    {te(`zoneType.${p.zone.zone_type}`)}
                  </span>
                </TD>
                <TD label={t("fields.required_inductions")}>
                  <span className="ltr">
                    {p.required_inductions.join(", ") || "—"}
                  </span>
                </TD>
                <TD label={t("fields.airport_pass_area_code")}>
                  {p.airport_pass_area_code ? (
                    <Code>{p.airport_pass_area_code}</Code>
                  ) : (
                    "—"
                  )}
                </TD>
                <TD label={t("fields.access_permit_required")}>
                  {p.access_permit_required ? tc("yes") : tc("no")}
                </TD>
                <TD label={t("fields.adp_category_required")}>
                  {p.adp_category_required
                    ? te(`areaCategory.${p.adp_category_required}`)
                    : "—"}
                </TD>
                <TD label={t("fields.escort_ratio_max")}>
                  {p.escort_ratio_max ?? "—"}
                </TD>
                <TD label={t("fields.hook_requirements")}>
                  <span className="flex flex-wrap gap-1">
                    {p.hook_requirements.map((h) => (
                      <Code key={`${h.kind}-${h.code}`}>{h.code}</Code>
                    ))}
                  </span>
                </TD>
                <TD label={tc("actions")}>
                  {canEdit ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setEdit(p)}
                      data-testid="edit-zone-profile"
                    >
                      <Pencil aria-hidden />
                      {tc("edit")}
                    </Button>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState />
      )}
      {edit ? (
        <ZoneProfileDialog
          project={project}
          profile={edit}
          onClose={() => setEdit(null)}
        />
      ) : null}
    </div>
  );
}

function ZoneProfileDialog({
  project,
  profile,
  onClose,
}: {
  project: Schemas["ProjectRead"];
  profile: Schemas["ZoneAccessProfileRead"];
  onClose: () => void;
}) {
  const t = useTranslations("zoneProfiles");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const courses = useInductionCourses(project.id);
  const areas = usePassAreas(project.id, { enabled: project.is_airport });
  const [req, setReq] = useState<string[]>(profile.required_inductions);
  const [area, setArea] = useState(profile.airport_pass_area_code ?? "");
  const [permit, setPermit] = useState(profile.access_permit_required);
  const [adp, setAdp] = useState<Schemas["AreaCategory"] | "">(
    profile.adp_category_required ?? "",
  );
  const [avp, setAvp] = useState<Schemas["AreaCategory"] | "">(
    profile.avp_area_required ?? "",
  );
  const [ratio, setRatio] = useState(
    profile.escort_ratio_max != null ? String(profile.escort_ratio_max) : "",
  );
  const [lvp, setLvp] = useState(profile.lvp_withdrawal_required);
  const [ils, setIls] = useState(profile.ils_outage_notam_required);
  const [hooks, setHooks] = useState<Hook[]>(profile.hook_requirements);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const u = await unwrap(
        api.PATCH("/api/v1/zones/{zone_id}/access-profile", {
          params: { path: { zone_id: profile.zone.id } },
          body: {
            required_inductions: req,
            airport_pass_area_code: area || null,
            access_permit_required: permit,
            adp_category_required: adp || null,
            avp_area_required: avp || null,
            escort_ratio_max: ratio ? Number(ratio) : null,
            lvp_withdrawal_required: lvp,
            ils_outage_notam_required: ils,
            hook_requirements: hooks,
          },
        }),
      );
      qc.setQueryData(ak.zoneProfile(profile.zone.id), u);
      await qc.invalidateQueries({ queryKey: ["zone-access-profiles"] });
      await qc.invalidateQueries({ queryKey: ["eligibility"] });
      toast.success(tc("saved"));
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {t("editTitle", { code: profile.zone.code })}
          </DialogTitle>
          <DialogDescription>{t("tightenOnly")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <MultiSelect
            id="zp-req"
            label={t("fields.required_inductions")}
            options={(courses.data?.items ?? []).map((c) => ({
              value: c.code,
              label: c.code,
            }))}
            value={req}
            onChange={setReq}
            className="lg:w-full"
          />
          {project.is_airport ? (
            <FormField id="zp-area" label={t("fields.airport_pass_area_code")}>
              <Select value={area} onChange={(e) => setArea(e.target.value)}>
                <option value="">{tc("none")}</option>
                {(areas.data?.items ?? []).map((a) => (
                  <option key={a.id} value={a.code}>
                    {a.code} — {a.name_en}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          <CheckboxField
            id="zp-permit"
            label={t("fields.access_permit_required")}
          >
            <Checkbox
              checked={permit}
              onChange={(e) => setPermit(e.target.checked)}
            />
          </CheckboxField>
          {project.is_airport ? (
            <>
              <FormField id="zp-adp" label={t("fields.adp_category_required")}>
                <Select
                  value={adp}
                  onChange={(e) =>
                    setAdp(e.target.value as Schemas["AreaCategory"] | "")
                  }
                >
                  <option value="">{tc("none")}</option>
                  {AREA_CATEGORIES.map((x) => (
                    <option key={x} value={x}>
                      {te(`areaCategory.${x}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="zp-avp" label={t("fields.avp_area_required")}>
                <Select
                  value={avp}
                  onChange={(e) =>
                    setAvp(e.target.value as Schemas["AreaCategory"] | "")
                  }
                >
                  <option value="">{tc("none")}</option>
                  {AREA_CATEGORIES.map((x) => (
                    <option key={x} value={x}>
                      {te(`areaCategory.${x}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              <CheckboxField
                id="zp-lvp"
                label={t("fields.lvp_withdrawal_required")}
              >
                <Checkbox
                  checked={lvp}
                  onChange={(e) => setLvp(e.target.checked)}
                />
              </CheckboxField>
              <CheckboxField
                id="zp-ils"
                label={t("fields.ils_outage_notam_required")}
              >
                <Checkbox
                  checked={ils}
                  onChange={(e) => setIls(e.target.checked)}
                />
              </CheckboxField>
            </>
          ) : null}
          <FormField
            id="zp-ratio"
            label={t("fields.escort_ratio_max")}
            hint={t("ratioHint")}
          >
            <Input
              type="number"
              min={1}
              value={ratio}
              onChange={(e) => setRatio(e.target.value)}
            />
          </FormField>
          <div className="sm:col-span-2">
            <p className="mb-1 text-sm font-medium">
              {t("fields.hook_requirements")}
            </p>
            <HookEditor
              id="zp-hooks"
              value={hooks}
              onChange={setHooks}
              withTrades
            />
          </div>
        </div>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button
            onClick={() => void save()}
            disabled={busy || req.length === 0}
            data-testid="save-zone-profile"
          >
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ───────────────────────────── Pass categories and areas ───────────────────────────── */

export function PassSetupPage() {
  return (
    <ProjectGate>
      {(p) => (
        <AirportOnly project={p}>{<PassSetup project={p} />}</AirportOnly>
      )}
    </ProjectGate>
  );
}

function ColourDot({ colour }: { colour: Schemas["CardColour"] }) {
  const te = useTranslations("enums");
  const map: Record<Schemas["CardColour"], string> = {
    red: "#dc2626",
    blue: "#2563eb",
    green: "#16a34a",
    yellow: "#facc15",
    orange: "#f97316",
    white: "#ffffff",
    grey: "#6b7280",
  };
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden
        className="inline-block size-3 rounded-full border"
        style={{ background: map[colour] }}
      />
      {te(`cardColour.${colour}`)}
    </span>
  );
}

function PassSetup({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("passSetup");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const cats = usePassCategories(project.id);
  const areas = usePassAreas(project.id);
  const canEdit = canWrite(me, "access_settings.edit", project.id);
  const [cat, setCat] = useState<Schemas["PassCategoryRead"] | "new" | null>(
    null,
  );
  const [area, setArea] = useState<Schemas["PassAreaRead"] | "new" | null>(
    null,
  );
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">{t("categories")}</CardTitle>
          {canEdit ? (
            <Button
              size="sm"
              onClick={() => setCat("new")}
              data-testid="new-category"
            >
              <Plus aria-hidden />
              {t("newCategory")}
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {cats.isError ? (
            <ErrorState error={cats.error} onRetry={() => cats.refetch()} />
          ) : !cats.data ? (
            <LoadingState rows={2} />
          ) : cats.data.items.length ? (
            <Table data-testid="categories-table">
              <THead>
                <TR>
                  <TH>{t("fields.code")}</TH>
                  <TH>{t("fields.name")}</TH>
                  <TH>{t("fields.escorted")}</TH>
                  <TH>{t("fields.background_check_required")}</TH>
                  <TH>{t("fields.max_validity_days")}</TH>
                  <TH>{t("fields.card_colour")}</TH>
                  <TH>{t("fields.allows_adp")}</TH>
                  <TH>
                    <span className="sr-only">{tc("actions")}</span>
                  </TH>
                </TR>
              </THead>
              <TBody>
                {cats.data.items.map((c) => (
                  <TR key={c.id}>
                    <TD label={t("fields.code")}>
                      <Code>{c.code}</Code>{" "}
                      {c.active ? null : (
                        <StatusBadge status="inactive" label={t("inactive")} />
                      )}
                    </TD>
                    <TD label={t("fields.name")}>
                      {locale === "ar" ? c.name_ar : c.name_en}
                    </TD>
                    <TD label={t("fields.escorted")}>
                      {c.escorted ? tc("yes") : tc("no")}
                    </TD>
                    <TD label={t("fields.background_check_required")}>
                      {c.background_check_required ? tc("yes") : tc("no")}
                    </TD>
                    <TD label={t("fields.max_validity_days")}>
                      {c.max_validity_days}
                    </TD>
                    <TD label={t("fields.card_colour")}>
                      <ColourDot colour={c.card_colour} />
                    </TD>
                    <TD label={t("fields.allows_adp")}>
                      {c.allows_adp ? tc("yes") : tc("no")}
                    </TD>
                    <TD label={tc("actions")}>
                      {canEdit ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setCat(c)}
                        >
                          <Pencil aria-hidden />
                          {tc("edit")}
                        </Button>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState />
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">{t("areas")}</CardTitle>
          {canEdit ? (
            <Button
              size="sm"
              onClick={() => setArea("new")}
              data-testid="new-area"
            >
              <Plus aria-hidden />
              {t("newArea")}
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {areas.isError ? (
            <ErrorState error={areas.error} onRetry={() => areas.refetch()} />
          ) : !areas.data ? (
            <LoadingState rows={2} />
          ) : areas.data.items.length ? (
            <Table data-testid="areas-table">
              <THead>
                <TR>
                  <TH>{t("fields.code")}</TH>
                  <TH>{t("fields.name")}</TH>
                  <TH>{t("fields.area_kind")}</TH>
                  <TH>{t("fields.colour")}</TH>
                  <TH>{t("fields.zones")}</TH>
                  <TH>
                    <span className="sr-only">{tc("actions")}</span>
                  </TH>
                </TR>
              </THead>
              <TBody>
                {areas.data.items.map((a) => (
                  <TR key={a.id}>
                    <TD label={t("fields.code")}>
                      <Code>{a.code}</Code>{" "}
                      {a.active ? null : (
                        <StatusBadge status="inactive" label={t("inactive")} />
                      )}
                    </TD>
                    <TD label={t("fields.name")}>
                      {locale === "ar" ? a.name_ar : a.name_en}
                    </TD>
                    <TD label={t("fields.area_kind")}>
                      {te(`passAreaKind.${a.area_kind}`)}
                    </TD>
                    <TD label={t("fields.colour")}>
                      <ColourDot colour={a.colour} />
                    </TD>
                    <TD label={t("fields.zones")}>
                      <span className="ltr">
                        {a.zones.map((z) => z.code).join(", ") || "—"}
                      </span>
                    </TD>
                    <TD label={tc("actions")}>
                      {canEdit ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setArea(a)}
                        >
                          <Pencil aria-hidden />
                          {tc("edit")}
                        </Button>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyState />
          )}
        </CardContent>
      </Card>
      {cat ? (
        <CategoryDialog
          project={project}
          cat={cat === "new" ? null : cat}
          onClose={() => setCat(null)}
        />
      ) : null}
      {area ? (
        <AreaDialog
          project={project}
          area={area === "new" ? null : area}
          onClose={() => setArea(null)}
        />
      ) : null}
    </div>
  );
}

function CategoryDialog({
  project,
  cat,
  onClose,
}: {
  project: Schemas["ProjectRead"];
  cat: Schemas["PassCategoryRead"] | null;
  onClose: () => void;
}) {
  const t = useTranslations("passSetup");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [code, setCode] = useState(cat?.code ?? "");
  const [nameEn, setNameEn] = useState(cat?.name_en ?? "");
  const [nameAr, setNameAr] = useState(cat?.name_ar ?? "");
  const [escorted, setEscorted] = useState(cat?.escorted ?? false);
  const [bg, setBg] = useState(cat?.background_check_required ?? true);
  const [maxDays, setMaxDays] = useState(String(cat?.max_validity_days ?? 365));
  const [colour, setColour] = useState<Schemas["CardColour"]>(
    cat?.card_colour ?? "red",
  );
  const [allowsAdp, setAllowsAdp] = useState(cat?.allows_adp ?? false);
  const [hooks, setHooks] = useState<Hook[]>(cat?.hook_requirements ?? []);
  const [active, setActive] = useState(cat?.active ?? true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError(null);
    const body = {
      name_en: nameEn.trim(),
      name_ar: nameAr.trim(),
      escorted,
      background_check_required: bg,
      max_validity_days: Number(maxDays),
      card_colour: colour,
      allows_adp: escorted ? false : allowsAdp,
      hook_requirements: hooks,
      active,
    };
    try {
      if (cat)
        await unwrap(
          api.PATCH("/api/v1/airport-pass-categories/{category_id}", {
            params: { path: { category_id: cat.id } },
            body,
          }),
        );
      else
        await unwrap(
          api.POST("/api/v1/projects/{project_id}/airport-pass-categories", {
            params: { path: { project_id: project.id } },
            body: { ...body, code: code.trim().toUpperCase() },
          }),
        );
      await qc.invalidateQueries({ queryKey: ak.passCategories(project.id) });
      toast.success(tc("saved"));
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {cat ? t("editCategory") : t("newCategory")}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="pc-code" label={t("fields.code")} required>
            <Input
              className="ltr uppercase"
              maxLength={8}
              value={code}
              disabled={Boolean(cat)}
              onChange={(e) => setCode(e.target.value)}
            />
          </FormField>
          <FormField id="pc-colour" label={t("fields.card_colour")} required>
            <Select
              value={colour}
              onChange={(e) =>
                setColour(e.target.value as Schemas["CardColour"])
              }
            >
              {CARD_COLOURS.map((c) => (
                <option key={c} value={c}>
                  {te(`cardColour.${c}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="pc-name-en" label={t("fields.name_en")} required>
            <Input
              dir="ltr"
              maxLength={120}
              value={nameEn}
              onChange={(e) => setNameEn(e.target.value)}
            />
          </FormField>
          <FormField id="pc-name-ar" label={t("fields.name_ar")} required>
            <Input
              dir="rtl"
              maxLength={120}
              value={nameAr}
              onChange={(e) => setNameAr(e.target.value)}
            />
          </FormField>
          <FormField
            id="pc-days"
            label={t("fields.max_validity_days")}
            required
          >
            <Input
              type="number"
              min={1}
              value={maxDays}
              onChange={(e) => setMaxDays(e.target.value)}
            />
          </FormField>
          <CheckboxField id="pc-escorted" label={t("fields.escorted")}>
            <Checkbox
              checked={escorted}
              onChange={(e) => setEscorted(e.target.checked)}
            />
          </CheckboxField>
          <CheckboxField
            id="pc-bg"
            label={t("fields.background_check_required")}
          >
            <Checkbox checked={bg} onChange={(e) => setBg(e.target.checked)} />
          </CheckboxField>
          <CheckboxField id="pc-adp" label={t("fields.allows_adp")}>
            <Checkbox
              checked={!escorted && allowsAdp}
              disabled={escorted}
              onChange={(e) => setAllowsAdp(e.target.checked)}
            />
          </CheckboxField>
          <CheckboxField id="pc-active" label={t("active")}>
            <Checkbox
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
            />
          </CheckboxField>
          {!escorted && !bg ? (
            <Alert tone="warning" className="sm:col-span-2">
              {t("bgRequiredHint")}
            </Alert>
          ) : null}
          <div className="sm:col-span-2">
            <p className="mb-1 text-sm font-medium">
              {t("fields.hook_requirements")}
            </p>
            <HookEditor id="pc-hooks" value={hooks} onChange={setHooks} />
          </div>
        </div>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button
            onClick={() => void save()}
            disabled={busy || !code.trim() || !nameEn.trim() || !nameAr.trim()}
            data-testid="save-category"
          >
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AreaDialog({
  project,
  area,
  onClose,
}: {
  project: Schemas["ProjectRead"];
  area: Schemas["PassAreaRead"] | null;
  onClose: () => void;
}) {
  const t = useTranslations("passSetup");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const opts = useProjectOptions(project.id);
  const airside = opts.zones.filter((z) => z.zoneType === "airside");
  const [code, setCode] = useState(area?.code ?? "");
  const [nameEn, setNameEn] = useState(area?.name_en ?? "");
  const [nameAr, setNameAr] = useState(area?.name_ar ?? "");
  const [colour, setColour] = useState<Schemas["CardColour"]>(
    area?.colour ?? "red",
  );
  const [kind, setKind] = useState<Schemas["PassAreaKind"]>(
    area?.area_kind ?? "apron",
  );
  const [zones, setZones] = useState<string[]>(
    area?.zones.map((z) => z.id) ?? [],
  );
  const [active, setActive] = useState(area?.active ?? true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError(null);
    const body = {
      name_en: nameEn.trim(),
      name_ar: nameAr.trim(),
      colour,
      area_kind: kind,
      zone_ids: zones,
      active,
    };
    try {
      if (area)
        await unwrap(
          api.PATCH("/api/v1/airport-pass-areas/{area_id}", {
            params: { path: { area_id: area.id } },
            body,
          }),
        );
      else
        await unwrap(
          api.POST("/api/v1/projects/{project_id}/airport-pass-areas", {
            params: { path: { project_id: project.id } },
            body: { ...body, code: code.trim().toUpperCase() },
          }),
        );
      await qc.invalidateQueries({ queryKey: ak.passAreas(project.id) });
      toast.success(tc("saved"));
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{area ? t("editArea") : t("newArea")}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="pa-code" label={t("fields.code")} required>
            <Input
              className="ltr uppercase"
              maxLength={4}
              value={code}
              disabled={Boolean(area)}
              onChange={(e) => setCode(e.target.value)}
            />
          </FormField>
          <FormField id="pa-kind" label={t("fields.area_kind")} required>
            <Select
              value={kind}
              onChange={(e) =>
                setKind(e.target.value as Schemas["PassAreaKind"])
              }
            >
              {PASS_AREA_KINDS.map((c) => (
                <option key={c} value={c}>
                  {te(`passAreaKind.${c}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="pa-name-en" label={t("fields.name_en")} required>
            <Input
              dir="ltr"
              maxLength={120}
              value={nameEn}
              onChange={(e) => setNameEn(e.target.value)}
            />
          </FormField>
          <FormField id="pa-name-ar" label={t("fields.name_ar")} required>
            <Input
              dir="rtl"
              maxLength={120}
              value={nameAr}
              onChange={(e) => setNameAr(e.target.value)}
            />
          </FormField>
          <FormField id="pa-colour" label={t("fields.colour")} required>
            <Select
              value={colour}
              onChange={(e) =>
                setColour(e.target.value as Schemas["CardColour"])
              }
            >
              {CARD_COLOURS.map((c) => (
                <option key={c} value={c}>
                  {te(`cardColour.${c}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <MultiSelect
            id="pa-zones"
            label={t("fields.zones")}
            options={airside.map((z) => ({ value: z.value, label: z.label }))}
            value={zones}
            onChange={setZones}
            className="lg:w-full"
          />
          <CheckboxField id="pa-active" label={t("active")}>
            <Checkbox
              checked={active}
              onChange={(e) => setActive(e.target.checked)}
            />
          </CheckboxField>
        </div>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button
            onClick={() => void save()}
            disabled={busy || !code.trim() || !nameEn.trim() || !nameAr.trim()}
            data-testid="save-area"
          >
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
