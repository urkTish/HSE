"use client";
import { useTranslations } from "next-intl";
import { z } from "zod";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { FormField } from "@/components/common/form-field";
import { useMeData } from "@/components/shell/me-context";
import type { Schemas } from "@/lib/api/client";
import { useEngagements, useSites } from "@/lib/api/queries";
import { useCurrentProject } from "@/lib/current-project";
import { CONTRACTOR_SCOPED_ROLES, OFFICER_ASSIGNABLE_ROLES, ROLES } from "@/lib/enums";
import { emptyToNull } from "@/lib/forms";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can } from "@/lib/permissions";

export interface AssignmentValue {
  role: Schemas["Role"] | "";
  project_id: string;
  site_ids: string[];
  contractor_engagement_id: string;
  valid_from: string;
  valid_to: string;
}

export const emptyAssignment: AssignmentValue = {
  role: "",
  project_id: "",
  site_ids: [],
  contractor_engagement_id: "",
  valid_from: "",
  valid_to: "",
};

type TV = (key: "required" | "projectRequired" | "engagementRequired" | "endBeforeStart") => string;

export function assignmentSchema(tv: TV) {
  return z
    .object({
      role: z.union([z.enum(ROLES), z.literal("")]),
      project_id: z.string(),
      site_ids: z.array(z.string()),
      contractor_engagement_id: z.string(),
      valid_from: z.string(),
      valid_to: z.string(),
    })
    .superRefine((v, ctx) => {
      if (!v.role) ctx.addIssue({ code: "custom", path: ["role"], message: tv("required") });
      if (v.role && v.role !== "hse_manager" && !v.project_id) ctx.addIssue({ code: "custom", path: ["project_id"], message: tv("projectRequired") });
      if (v.role && CONTRACTOR_SCOPED_ROLES.includes(v.role) && !v.contractor_engagement_id) {
        ctx.addIssue({ code: "custom", path: ["contractor_engagement_id"], message: tv("engagementRequired") });
      }
      if (v.valid_from && v.valid_to && v.valid_to < v.valid_from) {
        ctx.addIssue({ code: "custom", path: ["valid_to"], message: tv("endBeforeStart") });
      }
    });
}

export function toAssignmentCreate(v: AssignmentValue): Schemas["RoleAssignmentCreate"] {
  const org = v.role === "hse_manager";
  return {
    role: v.role as Schemas["Role"],
    project_id: org ? null : emptyToNull(v.project_id),
    site_ids: org ? [] : v.site_ids,
    contractor_engagement_id: v.role && CONTRACTOR_SCOPED_ROLES.includes(v.role) ? emptyToNull(v.contractor_engagement_id) : null,
    valid_from: emptyToNull(v.valid_from),
    valid_to: emptyToNull(v.valid_to),
  };
}

type Errors = Partial<Record<keyof AssignmentValue, { message?: string }>>;

/** Controlled editor for one role assignment (role, project scope, sites, contractor engagement, validity). */
export function AssignmentFields({
  idPrefix,
  value,
  onChange,
  errors,
}: {
  idPrefix: string;
  value: AssignmentValue;
  onChange: (v: AssignmentValue) => void;
  errors?: Errors;
}) {
  const t = useTranslations("assignment");
  const tr = useTranslations("role");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const { projects } = useCurrentProject();
  const roleOptions = me.is_hse_manager ? [...ROLES] : [...OFFICER_ASSIGNABLE_ROLES];
  const projectOptions = projects.filter((p) => me.is_hse_manager || can(me, "user.invite", p.id));
  const needsProject = value.role !== "hse_manager";
  const needsEngagement = value.role !== "" && CONTRACTOR_SCOPED_ROLES.includes(value.role);
  const sites = useSites(needsProject ? value.project_id : "", { page_size: 100, sort: "code" });
  const engagements = useEngagements(needsProject ? value.project_id : "", { page_size: 200 }, needsEngagement);
  const set = (patch: Partial<AssignmentValue>) => onChange({ ...value, ...patch });

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField id={`${idPrefix}-role`} label={t("fields.role")} error={errors?.role?.message} required>
        <Select value={value.role} onChange={(e) => set({ role: e.target.value as Schemas["Role"] | "", contractor_engagement_id: "" })} data-testid="assignment-role">
          <option value="">{tc("select")}</option>
          {roleOptions.map((r) => (
            <option key={r} value={r}>
              {tr(r)}
            </option>
          ))}
        </Select>
      </FormField>
      {needsProject ? (
        <FormField id={`${idPrefix}-project`} label={t("fields.project")} error={errors?.project_id?.message} required>
          <Select value={value.project_id} onChange={(e) => set({ project_id: e.target.value, site_ids: [], contractor_engagement_id: "" })} data-testid="assignment-project">
            <option value="">{tc("select")}</option>
            {projectOptions.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code} — {name(p.name_en, p.name_ar)}
              </option>
            ))}
          </Select>
        </FormField>
      ) : (
        <p className="self-end text-sm text-muted-foreground">{t("orgWide")}</p>
      )}
      {needsEngagement && value.project_id ? (
        <FormField
          id={`${idPrefix}-engagement`}
          label={t("fields.contractor_engagement")}
          error={errors?.contractor_engagement_id?.message}
          hint={t("engagementRequired")}
          required
          className="sm:col-span-2"
        >
          <Select value={value.contractor_engagement_id} onChange={(e) => set({ contractor_engagement_id: e.target.value })} data-testid="assignment-engagement">
            <option value="">{tc("select")}</option>
            {(engagements.data?.items ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                {e.contractor.short_code} — {name(e.contractor.legal_name_en, e.contractor.legal_name_ar)}
              </option>
            ))}
          </Select>
        </FormField>
      ) : null}
      {needsProject && value.project_id ? (
        <fieldset className="sm:col-span-2">
          <legend className="mb-1 text-sm font-medium">{t("fields.sites")}</legend>
          <p className="mb-2 text-xs text-muted-foreground">{t("sitesHint")}</p>
          <div className="grid gap-1 sm:grid-cols-2">
            {(sites.data?.items ?? []).map((s) => (
              <label key={s.id} className="flex min-h-touch items-center gap-3 text-sm">
                <Checkbox
                  checked={value.site_ids.includes(s.id)}
                  onChange={(e) => set({ site_ids: e.target.checked ? [...value.site_ids, s.id] : value.site_ids.filter((x) => x !== s.id) })}
                />
                <span>
                  <span className="ltr">{s.code}</span> — {name(s.name_en, s.name_ar)}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}
      <FormField id={`${idPrefix}-from`} label={t("fields.valid_from")} error={errors?.valid_from?.message}>
        <Input type="date" value={value.valid_from} onChange={(e) => set({ valid_from: e.target.value })} />
      </FormField>
      <FormField id={`${idPrefix}-to`} label={t("fields.valid_to")} error={errors?.valid_to?.message}>
        <Input type="date" value={value.valid_to} onChange={(e) => set({ valid_to: e.target.value })} />
      </FormField>
    </div>
  );
}
