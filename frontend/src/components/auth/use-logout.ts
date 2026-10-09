"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api/client";
import { clearFieldCache } from "@/lib/field-offline";

export function useLogout() {
  const qc = useQueryClient();
  const router = useRouter();
  return useCallback(async () => {
    try {
      await api.POST("/api/v1/auth/logout");
    } finally {
      // P6d-6 / AC59: the 6d offline pack and unsent drafts never outlive the session on this device.
      await clearFieldCache().catch(() => undefined);
      qc.clear();
      router.replace({ pathname: "/login", query: { reason: "signed-out" } });
    }
  }, [qc, router]);
}
