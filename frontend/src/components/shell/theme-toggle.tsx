"use client";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { applyTheme, subscribeTheme, themeSnapshot, type ThemePreference } from "@/lib/theme";

const OPTIONS: { value: ThemePreference; Icon: typeof Sun }[] = [
  { value: "light", Icon: Sun },
  { value: "dark", Icon: Moon },
  { value: "system", Icon: Monitor },
];

/** Light / dark / follow-the-device switch. */
export function ThemeToggle() {
  const t = useTranslations("theme");
  const pref = useSyncExternalStore(subscribeTheme, themeSnapshot, () => "system" as const);
  const Current = OPTIONS.find((o) => o.value === pref)?.Icon ?? Monitor;

  function choose(v: ThemePreference) {
    applyTheme(v);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`${t("label")}: ${t(pref)}`} data-testid="theme-toggle">
          <Current aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44">
        <DropdownMenuLabel>{t("label")}</DropdownMenuLabel>
        {OPTIONS.map(({ value, Icon }) => (
          <DropdownMenuItem key={value} onSelect={() => choose(value)} aria-checked={pref === value} role="menuitemradio" data-testid={`theme-${value}`}>
            <Icon aria-hidden />
            <span className="flex-1">{t(value)}</span>
            {pref === value ? <Check aria-hidden className="text-primary" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
