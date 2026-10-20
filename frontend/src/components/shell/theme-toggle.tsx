"use client";
import { Check, Layers2, Monitor, Moon, Square, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  applySurface,
  applyTheme,
  subscribeSurface,
  subscribeTheme,
  surfaceSnapshot,
  themeSnapshot,
  type SurfacePreference,
  type ThemePreference,
} from "@/lib/theme";

const OPTIONS: { value: ThemePreference; Icon: typeof Sun }[] = [
  { value: "light", Icon: Sun },
  { value: "dark", Icon: Moon },
  { value: "system", Icon: Monitor },
];
// Surface (D-277): glass, solid, or decided by the device (solid on touch screens, glass with a mouse).
const SURFACES: { value: SurfacePreference; Icon: typeof Sun }[] = [
  { value: "glass", Icon: Layers2 },
  { value: "solid", Icon: Square },
  { value: "auto", Icon: Monitor },
];

/** Light / dark / follow-the-device switch, with the glass / solid surface choice below it. */
export function ThemeToggle() {
  const t = useTranslations("theme");
  const pref = useSyncExternalStore(subscribeTheme, themeSnapshot, () => "system" as const);
  const surface = useSyncExternalStore(subscribeSurface, surfaceSnapshot, () => "auto" as const);
  const Current = OPTIONS.find((o) => o.value === pref)?.Icon ?? Monitor;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`${t("label")}: ${t(pref)}`} data-testid="theme-toggle">
          <Current aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-48">
        <DropdownMenuLabel>{t("label")}</DropdownMenuLabel>
        {OPTIONS.map(({ value, Icon }) => (
          <DropdownMenuItem key={value} onSelect={() => applyTheme(value)} aria-checked={pref === value} role="menuitemradio" data-testid={`theme-${value}`}>
            <Icon aria-hidden />
            <span className="flex-1">{t(value)}</span>
            {pref === value ? <Check aria-hidden className="text-primary" /> : null}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuLabel>{t("surface")}</DropdownMenuLabel>
        {SURFACES.map(({ value, Icon }) => (
          <DropdownMenuItem
            key={value}
            onSelect={() => applySurface(value)}
            aria-checked={surface === value}
            role="menuitemradio"
            data-testid={`surface-${value}`}
          >
            <Icon aria-hidden />
            <span className="flex-1">{t(`surface_${value}`)}</span>
            {surface === value ? <Check aria-hidden className="text-primary" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
