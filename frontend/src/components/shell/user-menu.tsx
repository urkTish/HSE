"use client";
import { LogOut, UserRound } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useRouter } from "@/i18n/navigation";
import { useLogout } from "@/components/auth/use-logout";
import { useMeData } from "@/components/shell/me-context";
import { useLocalizedName } from "@/lib/i18n-helpers";

export function UserMenu() {
  const t = useTranslations("shell");
  const tn = useTranslations("nav");
  const me = useMeData();
  const name = useLocalizedName();
  const router = useRouter();
  const logout = useLogout();
  const display = name(me.full_name_en, me.full_name_ar);
  const initials = display
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] ?? "")
    .join("");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={t("userMenu")} data-testid="user-menu">
          <span aria-hidden className="flex size-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            {initials}
          </span>
          <span className="hidden max-w-40 truncate md:inline">{display}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>
          {t("signedInAs")}
          <span className="block truncate text-sm font-medium text-foreground ltr">{me.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => router.push("/profile")}>
          <UserRound aria-hidden />
          {tn("profile")}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void logout()} data-testid="logout">
          <LogOut aria-hidden className="rtl:-scale-x-100" />
          {t("logout")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
