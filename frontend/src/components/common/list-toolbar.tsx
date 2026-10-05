"use client";
import { Search } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

export function ListToolbar({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <div className="grid flex-1 gap-3 sm:grid-cols-2 lg:flex lg:flex-wrap lg:items-end">{children}</div>
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
