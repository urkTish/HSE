"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Toaster } from "sonner";
import { useLocale } from "next-intl";
import { ApiError } from "@/lib/api/client";
import { onAuthEvent } from "@/lib/api/auth-events";
import { usePathname, useRouter } from "@/i18n/navigation";

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        staleTime: 15_000,
        retry: (count, err) => !(err instanceof ApiError && err.status > 0 && err.status < 500) && count < 2,
      },
      mutations: { retry: false },
    },
  });
}

const PUBLIC_PATHS = ["/login", "/privacy", "/accept-invite", "/forgot-password", "/reset-password"];

function AuthEventBridge({ client }: { client: QueryClient }) {
  const router = useRouter();
  const pathname = usePathname();
  useEffect(
    () =>
      onAuthEvent((e) => {
        const onPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
        if (e === "privacy") {
          if (!pathname.startsWith("/privacy")) router.replace("/privacy");
          return;
        }
        if (onPublic) return;
        client.clear();
        const next = pathname && pathname !== "/" ? pathname : undefined;
        router.replace({
          pathname: "/login",
          query: { ...(e === "expired" ? { reason: "expired" } : {}), ...(next ? { next } : {}) },
        });
      }),
    [client, pathname, router],
  );
  return null;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(makeClient);
  const locale = useLocale();
  return (
    <QueryClientProvider client={client}>
      <AuthEventBridge client={client} />
      {children}
      <Toaster position={locale === "ar" ? "top-left" : "top-right"} richColors closeButton dir={locale === "ar" ? "rtl" : "ltr"} />
    </QueryClientProvider>
  );
}
