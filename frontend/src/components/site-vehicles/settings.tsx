"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FormField, FormSection } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { MutationError } from "@/components/common/states";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useSvRefresh } from "@/lib/api/site-vehicles";
import { useFormatters } from "@/lib/use-formatters";
import { GROUPS, PrototypeBadge, SvGate, SvSubNav, useSvCaps, useSvLabels } from "./common";

type S = Schemas;
const WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"] as const satisfies readonly S["Weekday"][];
const POLICIES = ["warn", "block"] as const satisfies readonly S["SiteVehPolicy"][];

/** 7b project settings (§3.5, capability 237, HSE Manager; SETTING_OUT_OF_RANGE). */
export function SiteVehicleSettingsPage() {
  return <SvGate allowOff>{(p, s) => <SettingsForm key={s.updated_at ?? "new"} project={p} s={s} />}</SvGate>;
}

function SettingsForm({ project, s }: { project: S["ProjectRead"]; s: S["SiteVehSettingsRead"] }) {
  const t = useTranslations("sv.settings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const l = useSvLabels();
  const caps = useSvCaps(project.id);
  const refresh = useSvRefresh();
  const { dateTime } = useFormatters(project.id);
  const [f, setF] = useState({
    site_vehicles_from: s.site_vehicles_from ?? "",
    driver_auth_validity_months: String(s.driver_auth_validity_months),
    defensive_driving_code: s.defensive_driving_code,
    bus_driving_code: s.bus_driving_code,
    driver_hook_policy: s.driver_hook_policy,
    driver_auth_policy: s.driver_auth_policy,
    rest_weekday: s.rest_weekday,
    journey_hint_km: String(s.journey_hint_km),
    journey_hint_night_from: s.journey_hint_night_from,
    journey_hint_night_to: s.journey_hint_night_to,
  });
  const [groups, setGroups] = useState<S["SiteVehDriverGroup"][]>(s.pre_use_required_groups);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const ro = !caps.settings;

  async function save() {
    setBusy(true);
    setError(null);
    const body: S["SiteVehSettingsUpdate"] = {
      site_vehicles_from: f.site_vehicles_from || null,
      driver_auth_validity_months: Number(f.driver_auth_validity_months),
      defensive_driving_code: f.defensive_driving_code.trim(),
      bus_driving_code: f.bus_driving_code.trim(),
      driver_hook_policy: f.driver_hook_policy,
      driver_auth_policy: f.driver_auth_policy,
      pre_use_required_groups: groups,
      rest_weekday: f.rest_weekday,
      journey_hint_km: Number(f.journey_hint_km),
      journey_hint_night_from: f.journey_hint_night_from,
      journey_hint_night_to: f.journey_hint_night_to,
    };
    try {
      await unwrap(api.PATCH("/api/v1/projects/{project_id}/site-vehicle-settings", { params: { path: { project_id: project.id } }, body }));
      await refresh();
      toast.success(tc("saved"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      data-testid="sv-settings"
    >
      <div>
        <PageHeader title={t("title")} badge={<PrototypeBadge />} description={t("subtitle", { code: project.code })} />
        {s.live ? <SvSubNav projectId={project.id} /> : null}
      </div>
      {!s.live ? (
        <Alert tone="info" data-testid="sv-settings-off">
          {t("off")}
        </Alert>
      ) : null}
      {ro ? <Alert tone="info">{t("readOnly")}</Alert> : null}
      <MutationError error={error} />
      <FormSection title={t("switch")}>
        <FormField id="svs-from" label={t("from")} hint={t("fromHint")}>
          <Input type="date" className="ltr" value={f.site_vehicles_from} onChange={set("site_vehicles_from")} disabled={ro} data-testid="svs-from" />
        </FormField>
        <FormField id="svs-rest" label={t("restWeekday")}>
          <Select value={f.rest_weekday} onChange={set("rest_weekday")} disabled={ro} data-testid="svs-rest">
            {WEEKDAYS.map((w) => (
              <option key={w} value={w}>
                {te(`weekday.${w}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <div className="sm:col-span-2">
          <CheckboxGroup id="svs-groups" legend={t("preUseGroups")} options={GROUPS.map((g) => ({ value: g, label: l.group(g) }))} value={groups} onChange={setGroups} disabled={ro} hint={t("preUseGroupsHint")} />
        </div>
      </FormSection>
      <FormSection title={t("drivers")}>
        <FormField id="svs-months" label={t("validityMonths")} hint={t("validityHint")}>
          <Input type="number" inputMode="numeric" min={12} max={36} className="ltr" value={f.driver_auth_validity_months} onChange={set("driver_auth_validity_months")} disabled={ro} data-testid="svs-months" />
        </FormField>
        <FormField id="svs-def" label={t("defCode")}>
          <Input className="ltr" maxLength={20} value={f.defensive_driving_code} onChange={set("defensive_driving_code")} disabled={ro} data-testid="svs-def" />
        </FormField>
        <FormField id="svs-bus" label={t("busCode")}>
          <Input className="ltr" maxLength={20} value={f.bus_driving_code} onChange={set("bus_driving_code")} disabled={ro} />
        </FormField>
        <FormField id="svs-hook" label={t("hookPolicy")} hint={t("hookPolicyHint")}>
          <Select value={f.driver_hook_policy} onChange={set("driver_hook_policy")} disabled={ro} data-testid="svs-hook">
            {POLICIES.map((p) => (
              <option key={p} value={p}>
                {l.policy(p)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="svs-auth" label={t("authPolicy")} hint={t("authPolicyHint")}>
          <Select value={f.driver_auth_policy} onChange={set("driver_auth_policy")} disabled={ro} data-testid="svs-auth">
            {POLICIES.map((p) => (
              <option key={p} value={p}>
                {l.policy(p)}
              </option>
            ))}
          </Select>
        </FormField>
      </FormSection>
      <FormSection title={t("journeys")} description={t("journeysHint")}>
        <FormField id="svs-km" label={t("hintKm")} hint={t("hintKmRange")}>
          <Input type="number" inputMode="numeric" min={50} max={500} className="ltr" value={f.journey_hint_km} onChange={set("journey_hint_km")} disabled={ro} data-testid="svs-km" />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField id="svs-night-from" label={t("nightFrom")}>
            <Input type="time" className="ltr" value={f.journey_hint_night_from} onChange={set("journey_hint_night_from")} disabled={ro} />
          </FormField>
          <FormField id="svs-night-to" label={t("nightTo")}>
            <Input type="time" className="ltr" value={f.journey_hint_night_to} onChange={set("journey_hint_night_to")} disabled={ro} />
          </FormField>
        </div>
      </FormSection>
      {s.updated_at ? <p className="text-xs text-muted-foreground">{t("updated", { at: dateTime(s.updated_at), by: s.updated_by?.full_name_en ?? "—" })}</p> : null}
      {ro ? null : (
        <div>
          <Button type="submit" disabled={busy} data-testid="svs-save">
            {busy ? tc("saving") : tc("save")}
          </Button>
        </div>
      )}
    </form>
  );
}
