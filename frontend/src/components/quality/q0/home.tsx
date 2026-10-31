"use client";
import { AlertOctagon, ClipboardX, Inbox, ScanEye } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import { useQAwaiting, useQHome } from "@/lib/api/quality/q0";
import { useFormatters } from "@/lib/use-formatters";
import { ClassBadge, ProfileBadge, QGate, StatusBadge, useQCaps, useQLabels, type Project } from "./common";

/** Quality home `/quality` (spec 8-quality Q-NAV-02): big phone buttons, counts, stop-use banner. */
export function QualityHomePage() {
  return <QGate>{(p) => <Home project={p} />}</QGate>;
}

function Tile({ label, value, href, tone, testId }: { label: string; value: number; href?: string; tone?: "danger" | "warning"; testId: string }) {
  const body = (
    <Card className="h-full" data-testid={testId} data-value={value}>
      <CardContent className="flex flex-col gap-1 p-4">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <span className={`ltr text-2xl font-semibold ${tone === "danger" && value ? "text-danger" : tone === "warning" && value ? "text-warning" : ""}`}>{value}</span>
      </CardContent>
    </Card>
  );
  return href ? (
    <Link href={href} className="block rounded-xl focus-visible:outline-2">
      {body}
    </Link>
  ) : (
    body
  );
}

function Home({ project }: { project: Project }) {
  const t = useTranslations("quality.home");
  const { l, recordType } = useQLabels();
  const caps = useQCaps(project.id);
  const q = useQHome(project.id);
  const ar = useLocale() === "ar";
  const { date } = useFormatters(project.id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const h = q.data;
  if (!h) return null;
  return (
    <div>
      <PageHeader title={t("title")} badge={<ProfileBadge profile={h.sector_profile} />} description={t("subtitle", { project: project.code })} />
      {h.stop_use_alerts.map((a) => (
        <Alert tone="danger" key={String(a.id)} className="mb-3" data-testid="q-stop-use">
          <p className="font-medium">
            {t("stopUse")}: <Link href={`/quality/alerts/${a.id}`} className="underline">{String(a.alert_no ?? "")}</Link>
          </p>
          <p>{String((ar ? a.title_ar : a.title_en) ?? "")}</p>
        </Alert>
      ))}
      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {caps.write("ncr.raise") ? (
          <Button asChild size="lg" className="min-h-16 text-base" data-testid="q-raise-ncr">
            <Link href="/quality/ncrs/new">
              <ClipboardX aria-hidden />
              {t("raiseNcr")}
            </Link>
          </Button>
        ) : null}
        {caps.write("ncr.raise") ? (
          <Button asChild size="lg" variant="outline" className="min-h-16 text-base" data-testid="q-new-observation">
            <Link href="/quality/observations?new=1">
              <ScanEye aria-hidden />
              {t("observation")}
            </Link>
          </Button>
        ) : null}
        <Button asChild size="lg" variant="outline" className="min-h-16 text-base" data-testid="q-awaiting-button">
          <Link href="/quality/awaiting">
            <Inbox aria-hidden />
            {t("awaiting")}
            <Badge tone={h.awaiting_count ? "warning" : "neutral"} className="ms-2 ltr">
              {h.awaiting_count}
            </Badge>
          </Link>
        </Button>
      </div>
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Tile label={t("open")} value={h.ncr_open} href="/quality/ncrs?open_only=true" testId="q-tile-open" />
        <Tile label={l("ncr_class", "critical")} value={h.ncr_by_class.critical ?? 0} href="/quality/ncrs?open_only=true&classification=critical" tone="danger" testId="q-tile-critical" />
        <Tile label={l("ncr_class", "major")} value={h.ncr_by_class.major ?? 0} href="/quality/ncrs?open_only=true&classification=major" tone="warning" testId="q-tile-major" />
        <Tile label={l("ncr_class", "minor")} value={h.ncr_by_class.minor ?? 0} href="/quality/ncrs?open_only=true&classification=minor" testId="q-tile-minor" />
        <Tile label={t("overdue")} value={h.ncr_overdue} href="/quality/ncrs?overdue=true" tone="danger" testId="q-tile-overdue" />
        <Tile label={t("containmentOverdue")} value={h.containment_overdue} tone="danger" testId="q-tile-containment" />
      </div>
      {h.tiles.length ? (
        <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-6">
          {h.tiles.map((x) => (
            <Tile key={String(x.code)} label={String(ar ? x.label_ar : x.label_en)} value={Number(x.value)} href={x.href ? String(x.href) : undefined} testId={`q-tile-${String(x.code)}`} />
          ))}
        </div>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("myNcrs")}</CardTitle>
          </CardHeader>
          <CardContent>
            {h.my_open_ncrs.length ? (
              <ul className="flex flex-col gap-2" data-testid="q-my-ncrs">
                {h.my_open_ncrs.map((n) => (
                  <li key={String(n.id)} className="flex flex-wrap items-center gap-2">
                    <Link href={`/quality/ncrs/${n.id}`} className="ltr font-medium text-primary hover:underline">
                      {String(n.ncr_no ?? "")}
                    </Link>
                    <ClassBadge value={String(n.classification ?? "")} />
                    <StatusBadge kind="ncr_status" value={String(n.status)} />
                    <span className="min-w-0 flex-1 truncate text-sm" dir="auto">
                      {String(n.title)}
                    </span>
                    {n.target_close_date ? <span className="text-xs text-muted-foreground">{date(String(n.target_close_date))}</span> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message={t("noMyNcrs")} />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("byStatus")}</CardTitle>
          </CardHeader>
          <CardContent>
            <Table compact stack={false} data-testid="q-by-status">
              <THead>
                <TR>
                  <TH>{t("status")}</TH>
                  <TH className="text-end">{t("count")}</TH>
                </TR>
              </THead>
              <TBody>
                {Object.entries(h.ncr_by_status).map(([k, v]) => (
                  <TR key={k}>
                    <TD>
                      <StatusBadge kind="ncr_status" value={k} />
                    </TD>
                    <TD className="ltr text-end">{v}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      </div>
      {h.steps_without_rp.length ? (
        <Alert tone="warning" className="mt-4" data-testid="q-steps-without-rp">
          <p className="flex items-center gap-1 font-medium">
            <AlertOctagon aria-hidden className="size-4" />
            {t("stepsWithoutRp")}
          </p>
          <ul className="mt-1 list-disc ps-5">
            {h.steps_without_rp.map((s) => (
              <li key={`${s.record_id}-${s.step}`}>
                <Link href={String(s.link_path)} className="ltr underline">
                  {String(s.ref)}
                </Link>{" "}
                · {recordType(String(s.record_type))} · {String(s.step)}
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}
    </div>
  );
}

/** "Awaiting my sign-off" `/quality/awaiting` (Q-RPM-11): every part, oldest first. */
export function AwaitingPage() {
  return <QGate>{(p) => <Awaiting project={p} />}</QGate>;
}

function Awaiting({ project }: { project: Project }) {
  const t = useTranslations("quality.awaiting");
  const { recordType, step } = useQLabels();
  const q = useQAwaiting(project.id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const items = q.data?.items ?? [];
  const groups = new Map<string, typeof items>();
  for (const i of items) groups.set(i.record_type, [...(groups.get(i.record_type) ?? []), i]);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} badge={<Badge tone={items.length ? "warning" : "neutral"} className="ltr" data-testid="q-awaiting-count">{items.length}</Badge>} />
      {items.length === 0 ? <EmptyState message={t("empty")} /> : null}
      {[...groups.entries()].map(([type, rows]) => (
        <section key={type} className="mb-5">
          <h2 className="mb-2 text-sm font-semibold">{recordType(type)}</h2>
          <ul className="flex flex-col gap-2" data-testid="q-awaiting-list">
            {rows.map((r) => (
              <li key={`${r.record_id}-${r.step}`}>
                <Link href={r.link_path} className="glass flex flex-wrap items-center gap-2 rounded-lg border p-3 hover:bg-accent" data-testid="q-awaiting-item" data-ref={r.ref} data-step={r.step}>
                  <span className="ltr font-medium">{r.ref}</span>
                  <Badge tone="info">{step(r.record_type, r.step)}</Badge>
                  <span className="min-w-0 flex-1 truncate text-sm" dir="auto">
                    {r.title}
                  </span>
                  <span className="text-xs text-muted-foreground">{t("waiting", { h: r.waiting_hours })}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
