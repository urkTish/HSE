"use client";
import { Pencil } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useLocalizedName } from "@/lib/i18n-helpers";

type Member = Schemas["HseTeamMember"];
const POSITIONS = ["hse_manager", "hse_engineer", "hse_supervisor", "hse_officer", "hse_inspector", "other"] as const satisfies readonly Schemas["HsePosition"][];
const KEY = ["hse-team"] as const;

/** D-270: the HSE department as a reporting tree; the HSE Manager sets positions and lines. */
export function HseTeamPage() {
  const t = useTranslations("hseTeam");
  const me = useMeData();
  const q = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/v1/hse-team")) });
  const [editing, setEditing] = useState<Member | null>(null);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const items = q.data.items;
  const ids = new Set(items.map((m) => m.id));
  const children = new Map<string | null, Member[]>();
  for (const m of items) {
    const parent = m.reports_to_user_id && ids.has(m.reports_to_user_id) ? m.reports_to_user_id : null;
    children.set(parent, [...(children.get(parent) ?? []), m]);
  }

  const branch = (parent: string | null, depth: number) => (
    <ul className={depth ? "ms-4 border-s ps-4" : ""} aria-label={depth ? undefined : t("title")}>
      {(children.get(parent) ?? []).map((m) => (
        <li key={m.id} className="py-1">
          <Row member={m} canEdit={me.is_hse_manager} onEdit={() => setEditing(m)} />
          {children.has(m.id) ? branch(m.id, depth + 1) : null}
        </li>
      ))}
    </ul>
  );

  return (
    <div data-testid="hse-team">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <Card>
        <CardContent className="pt-6">{items.length === 0 ? <EmptyState message={t("empty")} /> : branch(null, 0)}</CardContent>
      </Card>
      {editing ? <EditDialog member={editing} team={items} onClose={() => setEditing(null)} /> : null}
    </div>
  );
}

function Row({ member: m, canEdit, onEdit }: { member: Member; canEdit: boolean; onEdit: () => void }) {
  const t = useTranslations("hseTeam");
  const name = useLocalizedName();
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-2 py-1.5 hover:bg-muted/50" data-testid="team-member">
      <span className="font-medium">{name(m.full_name_en, m.full_name_ar)}</span>
      <span className="text-sm text-muted-foreground">{m.hse_position ? t(`position.${m.hse_position}`) : t("noPosition")}</span>
      {m.job_title ? <span className="text-xs text-muted-foreground">· {m.job_title}</span> : null}
      {canEdit ? (
        <Button size="sm" variant="ghost" className="ms-auto" onClick={onEdit} aria-label={`${t("edit")} ${name(m.full_name_en, m.full_name_ar)}`} data-testid="edit-member">
          <Pencil aria-hidden />
          {t("edit")}
        </Button>
      ) : null}
    </div>
  );
}

function EditDialog({ member: m, team, onClose }: { member: Member; team: Member[]; onClose: () => void }) {
  const t = useTranslations("hseTeam");
  const tc = useTranslations("common");
  const name = useLocalizedName();
  const qc = useQueryClient();
  const [position, setPosition] = useState<Schemas["HsePosition"] | "">(m.hse_position ?? "");
  const [boss, setBoss] = useState(m.reports_to_user_id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PATCH("/api/v1/hse-team/{user_id}", {
          params: { path: { user_id: m.id } },
          body: { hse_position: position || null, reports_to_user_id: boss || null },
        }),
      );
      await qc.invalidateQueries({ queryKey: KEY });
      toast.success(tc("saved"));
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{name(m.full_name_en, m.full_name_ar)}</DialogTitle>
        </DialogHeader>
        <FormField id="team-position" label={t("fields.position")}>
          <Select value={position} onChange={(e) => setPosition(e.target.value as Schemas["HsePosition"] | "")} data-testid="team-position">
            <option value="">{t("noPosition")}</option>
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {t(`position.${p}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="team-boss" label={t("fields.reportsTo")}>
          <Select value={boss} onChange={(e) => setBoss(e.target.value)} data-testid="team-boss">
            <option value="">{t("top")}</option>
            {team
              .filter((x) => x.id !== m.id)
              .map((x) => (
                <option key={x.id} value={x.id}>
                  {name(x.full_name_en, x.full_name_ar)}
                </option>
              ))}
          </Select>
        </FormField>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void save()} disabled={busy} data-testid="team-save">
            {busy ? tc("saving") : tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
