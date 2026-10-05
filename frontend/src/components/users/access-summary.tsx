"use client";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Link } from "@/i18n/navigation";
import type { Me } from "@/lib/permissions";

export function AccessSummary({ me }: { me: Me }) {
  const t = useTranslations("home");
  const tr = useTranslations("role");
  const tc = useTranslations("common");
  return (
    <ul className="flex flex-col gap-2 text-sm" data-testid="access-summary">
      {me.is_hse_manager ? (
        <li className="flex flex-wrap items-center gap-2">
          <Badge tone="info">{tr("hse_manager")}</Badge>
          <span className="text-muted-foreground">{t("orgWide")}</span>
        </li>
      ) : null}
      {me.projects.map((p) => (
        <li key={p.project_id} className="flex flex-wrap items-center gap-2">
          <Link href={`/projects/${p.project_id}`} className="font-medium text-primary hover:underline ltr">
            {p.project_code}
          </Link>
          {p.roles.map((r) => (
            <Badge key={r} tone="neutral">
              {tr(r)}
            </Badge>
          ))}
          {p.read_only ? <Badge tone="warning">{tc("readOnly")}</Badge> : null}
        </li>
      ))}
    </ul>
  );
}
