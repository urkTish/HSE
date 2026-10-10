"use client";
import { ChartNoAxesColumn, Pencil } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { HistoryPanel } from "@/components/common/history-panel";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { TransitionActions } from "@/components/common/transition-actions";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { keys, useContractor } from "@/lib/api/queries";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { CONTRACTOR_FLOW } from "@/lib/workflows";
import { useFormatters } from "@/lib/use-formatters";

type Kind = "submit" | "approve" | "returnToDraft" | "suspend" | "reinstate" | "demobilise" | "blacklist" | "liftBlacklist";

export function ContractorDetail({ contractorId }: { contractorId: string }) {
  const t = useTranslations("contractor");
  const tn = useTranslations("nav");
  const tc = useTranslations("common");
  const td = useTranslations("scDesign");
  const me = useMeData();
  const qc = useQueryClient();
  const name = useLocalizedName();
  const { date, dateTime } = useFormatters();
  const q = useContractor(contractorId);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const c = q.data;
  const canCreate = can(me, "contractor.create");
  const canApprove = can(me, "contractor.approve");
  const hasContact = Boolean(c.primary_contact_name || c.primary_contact_mobile || c.primary_contact_email);
  const options = CONTRACTOR_FLOW[c.status]
    .filter((e) => (e.approve ? canApprove : canCreate))
    .map((e) => ({
      to: e.to,
      reasonRequired: e.reasonRequired,
      label: e.kind ? t(`actions.${e.kind as Kind}`) : undefined,
      destructive: e.to === "blacklisted",
      warning: e.to === "blacklisted" ? t("blacklistWarning") : undefined,
    }));

  async function transition(to: Schemas["ContractorStatus"], reason: string | null) {
    const res = await unwrap(
      api.POST("/api/v1/contractors/{contractor_id}/transitions", { params: { path: { contractor_id: c.id } }, body: { to_status: to, reason } }),
    );
    qc.setQueryData(keys.contractor(c.id), res);
    await qc.invalidateQueries({ queryKey: ["contractors"] });
    await qc.invalidateQueries({ queryKey: ["history"] });
    await qc.invalidateQueries({ queryKey: ["engagements"] });
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("contractors"), href: "/contractors" }, { label: c.short_code }]} />
      <PageHeader
        title={<span data-testid="contractor-title">{name(c.legal_name_en, c.legal_name_ar)}</span>}
        badge={
          <>
            <Badge tone="neutral" className="ltr">
              {c.short_code}
            </Badge>
            <StatusBadge status={c.status} label={t(`status.${c.status}`)} />
          </>
        }
        actions={
          <>
            {canWrite(me, "scorecard.manage") ? (
              <Button variant="outline" asChild>
                <Link href={`/contractors/${c.id}/performance`} data-testid="contractor-performance">
                  <ChartNoAxesColumn aria-hidden />
                  {td("performance")}
                </Link>
              </Button>
            ) : null}
            {canCreate && c.status !== "blacklisted" ? (
              <Button variant="outline" asChild>
                <Link href={`/contractors/${c.id}/edit`}>
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Link>
              </Button>
            ) : null}
          </>
        }
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>{tc("details")}</CardTitle>
            </CardHeader>
            <CardContent>
              <FieldList>
                <FieldItem label={t("fields.legal_name_en")}>{c.legal_name_en}</FieldItem>
                <FieldItem label={t("fields.legal_name_ar")}>
                  <span lang="ar">{c.legal_name_ar}</span>
                </FieldItem>
                <FieldItem label={t("fields.contractor_category")}>{t(`category.${c.contractor_category}`)}</FieldItem>
                <FieldItem label={t("fields.cr_number")} ltr>{c.cr_number}</FieldItem>
                <FieldItem label={t("fields.cr_expiry_date")}>{date(c.cr_expiry_date)}</FieldItem>
                <FieldItem label={t("fields.vat_number")} ltr>{c.vat_number ?? "—"}</FieldItem>
                {c.status_reason ? <FieldItem label={t("fields.status_reason")}>{c.status_reason}</FieldItem> : null}
                <FieldItem label={tc("updatedAt")}>{dateTime(c.updated_at)}</FieldItem>
              </FieldList>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t("contact")}</CardTitle>
            </CardHeader>
            <CardContent>
              {hasContact ? (
                <FieldList>
                  <FieldItem label={t("fields.primary_contact_name")}>{c.primary_contact_name ?? "—"}</FieldItem>
                  <FieldItem label={t("fields.primary_contact_mobile")} ltr>{c.primary_contact_mobile ?? "—"}</FieldItem>
                  <FieldItem label={t("fields.primary_contact_email")} ltr>{c.primary_contact_email ?? "—"}</FieldItem>
                </FieldList>
              ) : (
                <p className="text-sm text-muted-foreground" data-testid="contact-hidden">
                  {t("contactHidden")}
                </p>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          {options.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("fields.status")}</CardTitle>
              </CardHeader>
              <CardContent>
                <TransitionActions current={c.status} options={options} statusLabel={(s) => t(`status.${s}`)} onTransition={transition} />
              </CardContent>
            </Card>
          ) : null}
          {can(me, "history.view") ? <HistoryPanel entityType="contractor" entityId={c.id} /> : null}
        </div>
      </div>
    </div>
  );
}
