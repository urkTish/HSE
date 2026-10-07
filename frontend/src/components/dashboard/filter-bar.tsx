"use client";
import { ChevronLeft, ChevronRight, RotateCcw, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { MultiSelect } from "@/components/common/multi-select";
import { useProjectOptions } from "@/components/common/pickers";
import { useMeData } from "@/components/shell/me-context";
import { useGates } from "@/lib/api/access";
import type { Schemas } from "@/lib/api/client";
import { ANCHORED_PERIODS, DASH_KEYS, shiftAnchor, type DashFilters } from "@/lib/dashboard-filters";
import { COMPARISON_KINDS, PERIOD_PRESETS } from "@/lib/enums";
import { can } from "@/lib/permissions";
import type { ParamValue } from "@/lib/url-state";
import { cn } from "@/lib/utils";

const ZONE_TYPES: Schemas["ZoneType"][] = ["airside", "landside", "other"];

export function FilterBar({
  projectId,
  filters: f,
  set,
  context,
}: {
  projectId: string;
  filters: DashFilters;
  set: (u: Record<string, ParamValue>, o?: { resetPage?: boolean }) => void;
  context?: Schemas["KpiContext"];
}) {
  const t = useTranslations("dashboard");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const opts = useProjectOptions(projectId);
  const gates = useGates(projectId, { enabled: Boolean(projectId) && !f.allProjects && (["access_kpi.view", "gate_log.view", "gate.manage"] as const).some((c) => can(me, c, projectId)) });
  const gateOptions = (gates.data?.items ?? []).map((g) => ({ value: g.id, label: g.gate_code }));
  const zones = opts.zones.filter((z) => f.siteIds.length === 0 || f.siteIds.includes(z.siteId)).filter((z) => !f.zoneType || z.zoneType === f.zoneType);
  const anchored = ANCHORED_PERIODS.includes(f.period);
  const anchor = f.anchor ?? context?.period.as_of ?? null;
  const PrevIcon = locale === "ar" ? ChevronRight : ChevronLeft;
  const NextIcon = locale === "ar" ? ChevronLeft : ChevronRight;
  // Period controls are always shown on desktop; scope filters (sites, zones, contractors, tiers, as-of) fold
  // behind "More filters" so the figures start above the fold. Phones fold everything behind one toggle.
  const [open, setOpen] = useState(false);
  const scopeCount = f.siteIds.length + f.zoneIds.length + f.engagementIds.length + f.tiers.length + f.gateIds.length + (f.zoneType ? 1 : 0) + (f.includeSubs ? 0 : 1) + (f.asOf ? 1 : 0);
  const active = scopeCount + (f.allProjects ? 1 : 0);
  const [scopeOpen, setScopeOpen] = useState(scopeCount > 0);

  return (
    <section aria-label={t("filters")} className="flex flex-col gap-3 rounded-xl border bg-surface p-3 shadow-xs print:hidden" data-testid="dashboard-filters">
      <Button
        type="button"
        variant="outline"
        className="lg:hidden"
        aria-expanded={open}
        aria-controls="dash-filter-body"
        onClick={() => setOpen((v) => !v)}
        data-testid="filters-toggle"
      >
        <SlidersHorizontal aria-hidden />
        {t("filters")}
        {active > 0 ? <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground">{active}</span> : null}
      </Button>
      <div id="dash-filter-body" className={open ? "flex flex-col gap-3" : "hidden flex-col gap-3 lg:flex"}>
        <div className="flex flex-wrap items-end gap-3">
          {me.is_hse_manager ? (
            <label className="flex min-h-11 items-center gap-2 text-sm">
              <Checkbox
                checked={f.allProjects}
                onChange={(e) =>
                  set({
                    all: e.target.checked ? "1" : null,
                    site: null,
                    zone: null,
                    eng: null,
                  })
                }
                data-testid="filter-all-projects"
              />
              {t("allProjects")}
            </label>
          ) : null}
          <div className="flex flex-col gap-1.5 lg:w-36">
            <Label htmlFor="f-period">{t("period")}</Label>
            <Select
              id="f-period"
              value={f.period}
              onChange={(e) =>
                set({
                  period: e.target.value === "month" ? null : e.target.value,
                  anchor: null,
                })
              }
              data-testid="filter-period"
            >
              {PERIOD_PRESETS.map((p) => (
                <option key={p} value={p}>
                  {te(`period.${p}`)}
                </option>
              ))}
            </Select>
          </div>
          {anchored && anchor ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="f-anchor">{t("anchor")}</Label>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  size="icon"
                  variant="outline"
                  aria-label={t("prevPeriod")}
                  onClick={() => set({ anchor: shiftAnchor(anchor, f.period, -1) })}
                  data-testid="period-prev"
                >
                  <PrevIcon aria-hidden />
                </Button>
                <Input id="f-anchor" type="date" className="w-40 lg:w-36" value={anchor} onChange={(e) => set({ anchor: e.target.value || null })} />
                <Button
                  type="button"
                  size="icon"
                  variant="outline"
                  aria-label={t("nextPeriod")}
                  onClick={() => set({ anchor: shiftAnchor(anchor, f.period, 1) })}
                  data-testid="period-next"
                >
                  <NextIcon aria-hidden />
                </Button>
              </div>
            </div>
          ) : null}
          {f.period === "custom" ? (
            <>
              <div className="flex flex-col gap-1.5 lg:w-40">
                <Label htmlFor="f-start">{t("start")}</Label>
                <Input id="f-start" type="date" value={f.start ?? ""} onChange={(e) => set({ start: e.target.value || null })} />
              </div>
              <div className="flex flex-col gap-1.5 lg:w-40">
                <Label htmlFor="f-end">{t("end")}</Label>
                <Input id="f-end" type="date" value={f.end ?? ""} onChange={(e) => set({ end: e.target.value || null })} />
              </div>
            </>
          ) : null}
          <MultiSelect
            id="f-cmp"
            label={t("compare")}
            options={COMPARISON_KINDS.map((c) => ({
              value: c,
              label: te(`comparison.${c}`),
            }))}
            value={f.compare.length ? f.compare : ["previous"]}
            onChange={(v) => set({ cmp: v.length === 1 && v[0] === "previous" ? null : v })}
            testId="filter-compare"
          />
          <Button
            type="button"
            variant="outline"
            className="hidden lg:inline-flex"
            aria-expanded={scopeOpen}
            aria-controls="dash-filter-scope"
            onClick={() => setScopeOpen((v) => !v)}
            data-testid="filters-more"
          >
            <SlidersHorizontal aria-hidden />
            {tc("moreFilters")}
            {scopeCount > 0 ? <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground">{scopeCount}</span> : null}
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="lg:w-control lg:px-0"
            title={t("reset")}
            onClick={() => set(Object.fromEntries(DASH_KEYS.map((k) => [k, null])))}
            data-testid="filter-reset"
          >
            <RotateCcw aria-hidden />
            <span className="lg:sr-only">{t("reset")}</span>
          </Button>
        </div>
        <div id="dash-filter-scope" className={cn("flex-wrap items-end gap-3 border-t pt-3", scopeOpen ? "flex" : open ? "flex lg:hidden" : "hidden")} data-testid="filters-scope">
          {!f.allProjects ? (
            <>
              <MultiSelect id="f-site" label={t("sites")} options={opts.sites} value={f.siteIds} onChange={(v) => set({ site: v, zone: null })} testId="filter-site" />
              <div className="flex flex-col gap-1.5 lg:w-36">
                <Label htmlFor="f-zt">{t("zoneType")}</Label>
                <Select id="f-zt" value={f.zoneType ?? ""} onChange={(e) => set({ zt: e.target.value || null, zone: null })} data-testid="filter-zone-type">
                  <option value="">{tc("all")}</option>
                  {ZONE_TYPES.map((z) => (
                    <option key={z} value={z}>
                      {te(`zoneType.${z}`)}
                    </option>
                  ))}
                </Select>
              </div>
              <MultiSelect id="f-zone" label={t("zones")} options={zones} value={f.zoneIds} onChange={(v) => set({ zone: v })} testId="filter-zone" />
              <MultiSelect
                id="f-eng"
                label={t("contractors")}
                options={opts.engagements}
                value={f.engagementIds}
                onChange={(v) => set({ eng: v })}
                allLabel={tc("anyContractor")}
                testId="filter-contractor"
              />
              {gateOptions.length ? <MultiSelect id="f-gate" label={t("gates")} options={gateOptions} value={f.gateIds} onChange={(v) => set({ gate: v })} testId="filter-gate" /> : null}
            </>
          ) : null}
          <MultiSelect
            id="f-tier"
            label={t("tiers")}
            options={[1, 2, 3].map((n) => ({
              value: String(n),
              label: t("tier", { n }),
            }))}
            value={f.tiers.map(String)}
            onChange={(v) => set({ tier: v })}
            testId="filter-tier"
          />
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <Checkbox checked={f.includeSubs} onChange={(e) => set({ subs: e.target.checked ? null : "0" })} data-testid="filter-subs" />
            {t("includeSubs")}
          </label>
          <div className="flex flex-col gap-1.5 lg:w-40">
            <Label htmlFor="f-asof">{t("asOf")}</Label>
            <Input id="f-asof" type="date" value={f.asOf ?? ""} onChange={(e) => set({ as_of: e.target.value || null })} data-testid="filter-as-of" />
          </div>
        </div>
      </div>
    </section>
  );
}
