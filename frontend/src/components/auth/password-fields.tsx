"use client";
import { z } from "zod";
import { meetsPasswordPolicy } from "@/lib/password";

type T = (key: "required" | "passwordPolicy" | "passwordMismatch") => string;

export function newPasswordSchema(tv: T) {
  return z
    .object({
      password: z.string().min(1, tv("required")).refine(meetsPasswordPolicy, tv("passwordPolicy")),
      confirm: z.string().min(1, tv("required")),
    })
    .refine((v) => v.password === v.confirm, { path: ["confirm"], message: tv("passwordMismatch") });
}
