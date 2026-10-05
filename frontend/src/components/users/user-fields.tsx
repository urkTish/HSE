"use client";
import { z } from "zod";
import { EMPLOYER_TYPES } from "@/lib/enums";

type TV = (key: "required" | "email" | "mobile" | "employerContractor" | "maxLength", values?: { max: number }) => string;

/** Shared profile fields of invite and edit forms. */
export function userProfileShape(tv: TV) {
  return {
    full_name_en: z.string().trim().min(1, tv("required")).max(120, tv("maxLength", { max: 120 })),
    full_name_ar: z.string().trim().max(120, tv("maxLength", { max: 120 })),
    mobile: z.string().trim().refine((v) => v === "" || /^\+[1-9]\d{7,14}$/.test(v), tv("mobile")),
    employer_type: z.enum(EMPLOYER_TYPES),
    employer_contractor_id: z.string(),
    job_title: z.string().trim().max(80, tv("maxLength", { max: 80 })),
    preferred_language: z.enum(["en", "ar"]),
  };
}
