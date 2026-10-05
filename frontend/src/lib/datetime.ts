/**
 * Date display rules (spec §5.5 rules 33–34, K2, K3):
 * - timestamps are UTC from the API and are shown in the project time zone (Asia/Riyadh);
 * - date-only values (YYYY-MM-DD) are calendar dates and are never shifted;
 * - optional Umm al-Qura Hijri date via ICU (`islamic-umalqura`), no manual arithmetic.
 */
export type DisplayLocale = "en" | "ar";

export interface DateDisplayPrefs {
  locale: DisplayLocale;
  timeZone: string;
  showHijri: boolean;
  digits: "western" | "arabic_indic";
  dateFormatEn: "DD MMM YYYY" | "DD/MM/YYYY";
}

export const DEFAULT_TIME_ZONE = "Asia/Riyadh";

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

function toDate(value: string | Date): Date {
  if (value instanceof Date) return value;
  if (DATE_ONLY.test(value)) return new Date(`${value}T12:00:00Z`);
  return new Date(value);
}

function zoneFor(value: string | Date, prefs: DateDisplayPrefs): string {
  return typeof value === "string" && DATE_ONLY.test(value) ? "UTC" : prefs.timeZone;
}

function numbering(prefs: DateDisplayPrefs): string {
  return prefs.digits === "arabic_indic" ? "arab" : "latn";
}

function gregorianLocale(prefs: DateDisplayPrefs): string {
  const base = prefs.locale === "ar" ? "ar" : "en-GB";
  return `${base}-u-ca-gregory-nu-${numbering(prefs)}`;
}

function part(parts: Intl.DateTimeFormatPart[], type: Intl.DateTimeFormatPartTypes): string {
  return parts.find((p) => p.type === type)?.value ?? "";
}

export function formatDate(value: string | Date | null | undefined, prefs: DateDisplayPrefs): string {
  if (!value) return "—";
  const d = toDate(value);
  if (Number.isNaN(d.getTime())) return "—";
  const timeZone = zoneFor(value, prefs);
  const numeric = prefs.locale === "en" && prefs.dateFormatEn === "DD/MM/YYYY";
  const parts = new Intl.DateTimeFormat(gregorianLocale(prefs), {
    timeZone,
    day: "2-digit",
    month: numeric ? "2-digit" : prefs.locale === "ar" ? "long" : "short",
    year: "numeric",
  }).formatToParts(d);
  const day = part(parts, "day");
  const month = part(parts, "month");
  const year = part(parts, "year");
  const greg = numeric ? `${day}/${month}/${year}` : `${day} ${month} ${year}`;
  return prefs.showHijri ? `${greg} · ${formatHijri(d, prefs, timeZone)}` : greg;
}

export function formatTime(value: string | Date, prefs: DateDisplayPrefs): string {
  const d = toDate(value);
  const parts = new Intl.DateTimeFormat(gregorianLocale(prefs), {
    timeZone: prefs.timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(d);
  return `${part(parts, "hour")}:${part(parts, "minute")}`;
}

export function formatDateTime(value: string | Date | null | undefined, prefs: DateDisplayPrefs): string {
  if (!value) return "—";
  const d = toDate(value);
  if (Number.isNaN(d.getTime())) return "—";
  const date = formatDate(d, { ...prefs, showHijri: false });
  const time = formatTime(d, prefs);
  const base = `${date} ${time}`;
  return prefs.showHijri ? `${base} · ${formatHijri(d, prefs, prefs.timeZone)}` : base;
}

/** Umm al-Qura Hijri date from ICU, e.g. "13 Rabiʻ II 1448 AH". */
export function formatHijri(value: string | Date, prefs: DateDisplayPrefs, timeZone?: string): string {
  const d = toDate(value);
  const base = prefs.locale === "ar" ? "ar-SA" : "en-GB";
  return new Intl.DateTimeFormat(`${base}-u-ca-islamic-umalqura-nu-${numbering(prefs)}`, {
    timeZone: timeZone ?? zoneFor(value, prefs),
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(d);
}

/** YYYY-MM-DD for "today" in the project time zone (rule 33). */
export function todayInZone(timeZone: string = DEFAULT_TIME_ZONE): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(),
  );
}

/** Day boundary of a local (project time zone, UTC+03:00) date as an ISO instant, for API filters. */
export function riyadhDayBoundary(date: string, end: boolean): string {
  return end ? `${date}T23:59:59.999+03:00` : `${date}T00:00:00+03:00`;
}
