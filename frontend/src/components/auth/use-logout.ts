"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api/client";

export function useLogout() {
  const qc = useQueryClient();
  const router = useRouter();
  return useCallback(async () => {
    try {
      await api.POST("/api/v1/auth/logout");
    } finally {
      qc.clear();
      router.replace({ pathname: "/login", query: { reason: "signed-out" } });
    }
  }, [qc, router]);
}
