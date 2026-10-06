"use client";
import { ChevronDown, Search, SlidersHorizontal } from "lucide-react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { Children, useId, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";

/**
 * Filters + list actions. On phones and tablets only the first filter (usually search) shows;
 * the rest fold behind "More filters" so the records are visible without scrolling. On desktop,
 * long toolbars (more than DESKTOP_VISIBLE + 1 filters) show the first DESKTOP_VISIBLE and fold the
 * rest. The toolbar opens by itself when the URL carries filters (e.g. a dashboard link), so an
 * applied filter is never hidden.
 */
const DESKTOP_VISIBLE = 4;
const NOT_FILTERS = new Set(["page", "project", "sort", "order"]);

export function ListToolbar({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  const t = useTranslations("common");
  const id = useId();
  const params = useSearchParams();
  const filtered = Array.from(params.keys()).some((k) => !NOT_FILTERS.has(k));
  const [open, setOpen] = useState(filtered);
  const count = Children.toArray(children).length;
  const collapsible = count > 2;
  const desktopFold = count > DESKTOP_VISIBLE + 1;
  return (
    <div className="mb-4 flex flex-col gap-3 rounded-xl border bg-surface p-3 shadow-xs sm:p-4 lg:flex-row lg:items-end lg:justify-between">
      <div
        id={id}
        className={cn(
          "grid flex-1 gap-3 sm:grid-cols-2 lg:flex lg:flex-wrap lg:items-end",
          collapsible && !open && "max-lg:[&>*:not(:first-child)]:hidden",
          desktopFold && !open && "lg:[&>*:nth-child(n+5)]:hidden",
        )}
      >
        {children}
      </div>
      {collapsible ? (
        <Button
          variant="ghost"
          size="sm"
          className={cn("self-start", desktopFold ? "lg:self-end" : "lg:hidden")}
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen(!open)}
        >
          <SlidersHorizontal aria-hidden />
          {open ? t("fewerFilters") : t("moreFilters")}
          <ChevronDown aria-hidden className={cn("transition-transform", open && "rotate-180")} />
        </Button>
      ) : null}
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

export function SearchFilter({
  id,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const t = useTranslations("common");
  return (
    <div className="flex flex-col gap-1.5 lg:w-64">
      <Label htmlFor={id}>{t("search")}</Label>
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input id={id} type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder ?? t("searchPlaceholder")} className="ps-9" />
      </div>
    </div>
  );
}

export function SelectFilter<V extends string>({
  id,
  label,
  value,
  onChange,
  options,
  allLabel,
}: {
  id: string;
  label: string;
  value: V | "";
  onChange: (v: V | "") => void;
  options: { value: V; label: string }[];
  allLabel?: string;
}) {
  const t = useTranslations("common");
  return (
    <div className="flex flex-col gap-1.5 lg:w-48">
      <Label htmlFor={id}>{label}</Label>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value as V | "")}>
        <option value="">{allLabel ?? t("all")}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </Select>
    </div>
  );
}
