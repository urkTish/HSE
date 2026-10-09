"use client";
import { Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { UserSelect } from "@/components/common/pickers";
import type { Schemas } from "@/lib/api/client";
import { CA_PRIORITIES, CONTROL_LEVELS, FINDING_SEVERITIES } from "@/lib/enums";

export interface FindingDraft {
  description: string;
  severity: Schemas["app__core__hse_enums__FindingSeverity"];
  ca_required: boolean;
  ca_title: string;
  control_level: Schemas["ControlLevel"];
  priority: Schemas["CaPriority"];
  owner_id: string;
  verifier_id: string;
  due_date: string;
}

export const emptyFinding = (): FindingDraft => ({
  description: "",
  severity: "medium",
  ca_required: false,
  ca_title: "",
  control_level: "administrative",
  priority: "medium",
  owner_id: "",
  verifier_id: "",
  due_date: "",
});

/** Inspection findings; a finding that needs a CA creates it atomically with the inspection (N-4). */
export function toFindingInput(f: FindingDraft): Schemas["app__schemas__inspections__FindingInput"] {
  return {
    description: f.description.trim(),
    severity: f.severity,
    ca_required: f.ca_required,
    ca_id: null,
    corrective_action: f.ca_required
      ? {
          title: f.ca_title.trim() || f.description.trim().slice(0, 150),
          description: f.description.trim(),
          control_level: f.control_level,
          priority: f.priority,
          owner_id: f.owner_id,
          verifier_id: f.verifier_id,
          due_date: f.due_date || null,
        }
      : null,
  };
}

export function findingsValid(list: FindingDraft[]): boolean {
  return list.every((f) => f.description.trim() && (!f.ca_required || (f.owner_id && f.verifier_id)));
}

export function FindingsEditor({ projectId, value, onChange }: { projectId: string; value: FindingDraft[]; onChange: (v: FindingDraft[]) => void }) {
  const t = useTranslations("inspections");
  const tca = useTranslations("ca");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const set = (i: number, patch: Partial<FindingDraft>) => onChange(value.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  return (
    <div className="flex flex-col gap-3" data-testid="findings-editor">
      {value.map((f, i) => (
        <div key={i} className="grid gap-3 rounded-md border p-3 sm:grid-cols-2" data-testid="finding-row">
          <FormField id={`f-${i}-desc`} label={t("fields.description")} required className="sm:col-span-2">
            <Textarea rows={2} maxLength={1000} value={f.description} onChange={(e) => set(i, { description: e.target.value })} />
          </FormField>
          <FormField id={`f-${i}-sev`} label={t("fields.severity")} required>
            <Select value={f.severity} onChange={(e) => set(i, { severity: e.target.value as Schemas["app__core__hse_enums__FindingSeverity"] })}>
              {FINDING_SEVERITIES.map((x) => (
                <option key={x} value={x}>
                  {te(`findingSeverity.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <label className="flex min-h-touch items-center gap-3 text-sm">
            <Checkbox checked={f.ca_required} onChange={(e) => set(i, { ca_required: e.target.checked })} data-testid={`f-${i}-ca-required`} />
            {t("caRequired")}
          </label>
          {f.ca_required ? (
            <fieldset className="grid gap-3 rounded-md bg-muted/40 p-3 sm:col-span-2 sm:grid-cols-2">
              <legend className="text-sm font-medium">{t("caInline")}</legend>
              <FormField id={`f-${i}-title`} label={tca("fields.title")} className="sm:col-span-2">
                <Input maxLength={150} value={f.ca_title} onChange={(e) => set(i, { ca_title: e.target.value })} />
              </FormField>
              <FormField id={`f-${i}-cl`} label={tca("fields.control_level")} required>
                <Select value={f.control_level} onChange={(e) => set(i, { control_level: e.target.value as Schemas["ControlLevel"] })}>
                  {CONTROL_LEVELS.map((x) => (
                    <option key={x} value={x}>
                      {te(`controlLevel.${x}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id={`f-${i}-pr`} label={tca("fields.priority")} required>
                <Select value={f.priority} onChange={(e) => set(i, { priority: e.target.value as Schemas["CaPriority"] })}>
                  {CA_PRIORITIES.map((x) => (
                    <option key={x} value={x}>
                      {te(`caPriority.${x}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id={`f-${i}-owner`} label={tca("fields.owner")} required>
                <UserSelect projectId={projectId} value={f.owner_id} onChange={(e) => set(i, { owner_id: e.target.value })} data-testid={`f-${i}-owner`} />
              </FormField>
              <FormField id={`f-${i}-verifier`} label={tca("fields.verifier")} required>
                <UserSelect projectId={projectId} value={f.verifier_id} onChange={(e) => set(i, { verifier_id: e.target.value })} data-testid={`f-${i}-verifier`} />
              </FormField>
              <FormField id={`f-${i}-due`} label={tca("fields.due_date")} hint={tca("dueDefaultHint")}>
                <Input type="date" value={f.due_date} onChange={(e) => set(i, { due_date: e.target.value })} />
              </FormField>
            </fieldset>
          ) : null}
          <div className="sm:col-span-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => onChange(value.filter((_, j) => j !== i))}>
              <Trash2 aria-hidden />
              {tc("delete")}
            </Button>
          </div>
        </div>
      ))}
      <div>
        <Button type="button" size="sm" variant="outline" onClick={() => onChange([...value, emptyFinding()])} data-testid="add-finding">
          <Plus aria-hidden />
          {t("addFinding")}
        </Button>
      </div>
    </div>
  );
}
