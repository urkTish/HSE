"use client";
import { Download } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { downloadFile, type Schemas } from "@/lib/api/client";
import { useErrorMessage } from "@/lib/i18n-helpers";

export function ExportButtons({
  dataset,
  params,
}: {
  dataset: Schemas["ExportDataset"];
  params?: Record<string, string | null | undefined>;
}) {
  const t = useTranslations("export");
  const msg = useErrorMessage();
  const [busy, setBusy] = useState<Schemas["ExportFormat"] | null>(null);

  async function run(format: Schemas["ExportFormat"]) {
    const qs = new URLSearchParams({ format });
    for (const [k, v] of Object.entries(params ?? {})) if (v) qs.set(k, v);
    setBusy(format);
    try {
      await downloadFile(`/api/v1/exports/${dataset}?${qs.toString()}`, `${dataset}.${format}`);
      toast.success(t("done"));
    } catch (e) {
      toast.error(`${t("failed")}: ${msg(e)}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex gap-2" role="group" aria-label={t("label")}>
      <Button variant="outline" size="sm" onClick={() => run("csv")} disabled={busy !== null} data-testid="export-csv">
        <Download aria-hidden />
        {t("csv")}
      </Button>
      <Button variant="outline" size="sm" onClick={() => run("xlsx")} disabled={busy !== null} data-testid="export-xlsx">
        <Download aria-hidden />
        {t("xlsx")}
      </Button>
    </div>
  );
}
