"use client";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
}) {
  const t = useTranslations("common");
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
      <span data-testid="total-records">{t("totalRecords", { count: total })}</span>
      {pages > 1 ? (
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
            <ChevronLeft aria-hidden className="rtl:rotate-180" />
            {t("previous")}
          </Button>
          <span>{t("pageOf", { page, pages })}</span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
            {t("next")}
            <ChevronRight aria-hidden className="rtl:rotate-180" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}
