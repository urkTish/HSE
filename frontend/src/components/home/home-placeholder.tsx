"use client";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/alert";
import { PageHeader } from "@/components/common/page-header";
import { AccessSummary } from "@/components/users/access-summary";
import { useMeData } from "@/components/shell/me-context";
import { useLocalizedName } from "@/lib/i18n-helpers";

/** Phase 0 home: the KPI dashboard replaces this in Phase 1. */
export function HomePlaceholder() {
  const t = useTranslations("home");
  const me = useMeData();
  const name = useLocalizedName();
  return (
    <div data-testid="home">
      <PageHeader title={t("welcome", { name: name(me.full_name_en, me.full_name_ar) })} />
      <Alert tone="info" className="mb-6">
        {t("placeholder")}
      </Alert>
      <Card>
        <CardHeader>
          <CardTitle>{t("yourAccess")}</CardTitle>
        </CardHeader>
        <CardContent>
          <AccessSummary me={me} />
        </CardContent>
      </Card>
    </div>
  );
}
