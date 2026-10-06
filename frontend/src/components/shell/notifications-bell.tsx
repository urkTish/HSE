"use client";
import { Bell } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useNotifications } from "@/lib/api/queries";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { entityRoute } from "@/lib/routes";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";

function hrefFor(n: Schemas["NotificationRead"]): string | null {
  if (n.entity_type === "audit_log") return "/audit-log";
  return entityRoute(n.entity_type, n.entity_id, n.project_id);
}

export function NotificationsBell() {
  const t = useTranslations("shell");
  const q = useNotifications(false);
  const qc = useQueryClient();
  const router = useRouter();
  const name = useLocalizedName();
  const { dateTime } = useFormatters();
  const [open, setOpen] = useState(false);
  const unread = q.data?.unread_count ?? 0;

  async function openItem(n: Schemas["NotificationRead"]) {
    if (!n.read_at) {
      await unwrap(api.POST("/api/v1/notifications/{notification_id}/read", { params: { path: { notification_id: n.id } } })).catch(
        () => undefined,
      );
      await qc.invalidateQueries({ queryKey: ["notifications"] });
    }
    const href = hrefFor(n);
    if (href) {
      setOpen(false);
      router.push(href);
    }
  }

  async function markAll() {
    await unwrap(api.POST("/api/v1/notifications/read-all")).catch(() => undefined);
    await qc.invalidateQueries({ queryKey: ["notifications"] });
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={`${t("notifications")} — ${t("unreadCount", { count: unread })}`} data-testid="notifications-bell">
          <Bell aria-hidden />
          {unread > 0 ? (
            <span className="absolute end-1 top-1 min-w-4 rounded-full bg-destructive px-1 text-center text-[11px] leading-4 font-semibold text-destructive-foreground ring-2 ring-surface">
              {unread > 99 ? "99+" : unread}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(22rem,calc(100vw-2rem))] p-0">
        <div className="flex min-h-12 items-center justify-between border-b px-3 py-2">
          <h2 className="text-sm font-semibold">{t("notifications")}</h2>
          {unread > 0 ? (
            <Button variant="link" size="sm" className="h-auto p-0" onClick={markAll}>
              {t("markAllRead")}
            </Button>
          ) : null}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {q.isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">{t("loadingNotifications")}</p>
          ) : (q.data?.items.length ?? 0) === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">{t("noNotifications")}</p>
          ) : (
            <ul>
              {q.data?.items.map((n) => (
                <li key={n.id} className="border-b last:border-0">
                  <button
                    type="button"
                    onClick={() => void openItem(n)}
                    className={cn(
                      "flex min-h-touch w-full flex-col gap-0.5 border-s-4 border-transparent px-3 py-2.5 text-start hover:bg-accent",
                      !n.read_at && "border-info bg-info-bg/60",
                    )}
                  >
                    <span className={cn("text-sm", !n.read_at && "font-semibold")}>{name(n.title_en, n.title_ar)}</span>
                    {n.body_en || n.body_ar ? <span className="text-xs text-muted-foreground">{name(n.body_en, n.body_ar)}</span> : null}
                    <time className="text-xs text-muted-foreground" dateTime={n.created_at}>
                      {dateTime(n.created_at)}
                    </time>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
