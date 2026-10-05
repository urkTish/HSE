"use client";
import { Building2, ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { useCurrentProject } from "@/lib/current-project";
import { useLocalizedName } from "@/lib/i18n-helpers";

const PROJECT_ROUTE = /^\/projects\/([0-9a-f-]{36})(?:\/(sites|zones|engagements|settings|edit))?/;

export function ProjectSwitcher() {
  const t = useTranslations("shell");
  const { projectId, projects, setProjectId } = useCurrentProject();
  const name = useLocalizedName();
  const pathname = usePathname();
  const router = useRouter();

  if (projects.length === 0) return <span className="px-2 text-sm text-muted-foreground">{t("noProjects")}</span>;

  function change(id: string) {
    setProjectId(id);
    const m = PROJECT_ROUTE.exec(pathname);
    if (m && m[1] !== id) {
      const section = m[2] && m[2] !== "edit" ? `/${m[2]}` : "";
      router.push(`/projects/${id}${section}`);
    }
  }

  return (
    <label className="flex w-full min-w-0 items-center gap-2 text-sm sm:w-auto">
      <span className="hidden shrink-0 text-xs font-medium text-muted-foreground xl:inline">{t("projectSwitcher")}</span>
      <span className="relative min-w-0 flex-1 sm:flex-none">
        <Building2 aria-hidden className="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <ChevronDown aria-hidden className="pointer-events-none absolute end-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <select
        aria-label={t("projectSwitcher")}
        data-testid="project-switcher"
        className="h-control-sm w-full min-w-0 appearance-none truncate rounded-md border border-input bg-surface ps-8 pe-8 text-base font-medium text-foreground hover:bg-accent sm:w-[min(22rem,40vw)] lg:text-sm"
        value={projectId ?? ""}
        onChange={(e) => change(e.target.value)}
      >
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.code} — {name(p.name_en, p.name_ar)}
          </option>
        ))}
      </select>
      </span>
    </label>
  );
}
