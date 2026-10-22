"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap } from "@/lib/api/client";
import { gb, licenceKey, useLicence, type Licence } from "@/lib/api/licence";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";

const STATE_TONE = { none: "neutral", active: "success", expired: "danger", invalid: "danger" } as const;

/** D-295: licence status, usage against the caps, trial terms and the renewal form (HSE Manager). */
export function LicencePage() {
  const t = useTranslations("licence");
  const q = useLicence();
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const l = q.data;
  return (
    <div data-testid="licence-page" className="flex flex-col gap-5">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        badge={
          <Badge tone={STATE_TONE[l.state]} data-testid="licence-state">
            {t(`state.${l.state}`)}
          </Badge>
        }
      />
      <div className="grid gap-5 lg:grid-cols-2">
        <StatusCard l={l} />
        <UsageCard l={l} />
      </div>
      {l.is_trial ? <TrialTerms l={l} /> : null}
      <RenewCard />
    </div>
  );
}

function Row({ label, children, testId }: { label: string; children: ReactNode; testId?: string }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-4 gap-y-0.5 border-b py-2 last:border-b-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium" data-testid={testId}>
        {children}
      </dd>
    </div>
  );
}

function StatusCard({ l }: { l: Licence }) {
  const t = useTranslations("licence");
  const { date, dateTime } = useFormatters();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("status")}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        {l.state === "none" ? (
          <p data-testid="licence-no-key">{t("noKey")}</p>
        ) : (
          <dl>
            {l.problem ? (
              <Row label={t("fields.problem")}>
                <span className="ltr">{l.problem}</span>
              </Row>
            ) : null}
            {l.customer ? <Row label={t("fields.customer")} testId="licence-customer">{l.customer}</Row> : null}
            {l.bundle ? <Row label={t("fields.bundle")} testId="licence-bundle">{t(`bundle.${l.bundle}`)}</Row> : null}
            {l.licence_id ? (
              <Row label={t("fields.licenceId")}>
                <span className="ltr">{l.licence_id}</span>
              </Row>
            ) : null}
            {l.issued_on ? <Row label={t("fields.issuedOn")}>{date(l.issued_on)}</Row> : null}
            {l.valid_until ? <Row label={t("fields.validUntil")} testId="licence-valid-until">{date(l.valid_until)}</Row> : null}
            {l.days_left !== null && l.days_left >= 0 ? <Row label={t("fields.daysLeft")} testId="licence-days-left">{l.days_left}</Row> : null}
            {l.source ? <Row label={t("fields.source")}>{t(`source.${l.source}`)}</Row> : null}
            {l.installed_at ? <Row label={t("fields.installedAt")}>{dateTime(l.installed_at)}</Row> : null}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

function Meter({ label, text, percent, testId }: { label: string; text: string; percent: number | null; testId: string }) {
  const pct = percent === null ? null : Math.min(100, Math.max(0, percent));
  return (
    <div className="flex flex-col gap-1.5 py-2" data-testid={testId}>
      <div className="flex flex-wrap justify-between gap-x-4 text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{text}</span>
      </div>
      {pct !== null ? (
        <div className="h-2 overflow-hidden rounded-full bg-muted" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <div className={cn("h-full rounded-full", pct >= 100 ? "bg-danger" : pct >= 80 ? "bg-warning" : "bg-primary")} style={{ width: `${pct}%` }} />
        </div>
      ) : null}
    </div>
  );
}

function UsageCard({ l }: { l: Licence }) {
  const t = useTranslations("licence.usage");
  const count = (u: Licence["projects"]) => (u.limit === null ? t("unlimited", { used: u.used }) : t("of", { used: u.used, limit: u.limit }));
  const s = l.storage;
  const used = gb(s.used_bytes);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col">
        <Meter label={t("projects")} text={count(l.projects)} percent={l.projects.percent} testId="licence-usage-projects" />
        <Meter label={t("users")} text={count(l.users)} percent={l.users.percent} testId="licence-usage-users" />
        <Meter label={t("ai")} text={count(l.ai_questions_month)} percent={l.ai_questions_month.percent} testId="licence-usage-ai" />
        <Meter
          label={t("storage")}
          text={s.limit_gb === null ? t("gbUnlimited", { used }) : t("gbOf", { used, limit: s.limit_gb })}
          percent={s.percent}
          testId="licence-usage-storage"
        />
        <p className="text-xs text-muted-foreground">{t("storageDetail", { files: gb(s.files_bytes), db: gb(s.database_bytes) })}</p>
        {s.warning ? (
          <Alert tone="warning" className="mt-3" data-testid="licence-storage-warning">
            {t("storageWarning", { percent: s.percent ?? 0 })}
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

function TrialTerms({ l }: { l: Licence }) {
  const t = useTranslations("licence.trialTerms");
  const { date } = useFormatters();
  return (
    <Card data-testid="licence-trial-terms">
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        <ul className="ms-5 list-disc space-y-1">
          <li>{t("t1")}</li>
          <li>{t("t2")}</li>
          <li>{t("t3")}</li>
          <li>{t("t4")}</li>
        </ul>
        {l.data_deletion_after ? <p className="mt-3 font-medium">{t("deletion", { date: date(l.data_deletion_after) })}</p> : null}
      </CardContent>
    </Card>
  );
}

function RenewCard() {
  const t = useTranslations("licence.renew");
  const me = useMeData();
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(api.PUT("/api/v1/licence", { body: { key } }));
      qc.setQueryData(licenceKey, next);
      setKey("");
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {me.is_hse_manager ? (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="licence-key">{t("label")}</Label>
              <Textarea
                id="licence-key"
                dir="ltr"
                rows={4}
                spellCheck={false}
                autoComplete="off"
                className="font-mono text-xs"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                aria-describedby="licence-key-hint"
                data-testid="licence-key-input"
              />
              <p id="licence-key-hint" className="text-xs text-muted-foreground">
                {t("hint")}
              </p>
            </div>
            <MutationError error={error} />
            <div>
              <Button type="submit" disabled={busy || key.trim().length < 10} data-testid="licence-key-save">
                {t("submit")}
              </Button>
            </div>
          </form>
        ) : (
          <p className="text-sm text-muted-foreground">{t("managerOnly")}</p>
        )}
      </CardContent>
    </Card>
  );
}
