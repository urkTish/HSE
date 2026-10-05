"use client";
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

  if (projects.length === 0) return <span className="text-sm text-muted-foreground">{t("noProjects")}</span>;

  function change(id: string) {
    setProjectId(id);
    const m = PROJECT_ROUTE.exec(pathname);
    if (m && m[1] !== id) {
      const section = m[2] && m[2] !== "edit" ? `/${m[2]}` : "";
      router.push(`/projects/${id}${section}`);
    }
  }

  return (
    <label className="flex min-w-0 items-center gap-2 text-sm">
      <span className="hidden text-muted-foreground sm:inline">{t("projectSwitcher")}</span>
      <select
        aria-label={t("projectSwitcher")}
        data-testid="project-switcher"
        className="h-9 max-w-[14rem] truncate rounded-md border border-input bg-surface px-2 text-sm sm:max-w-xs"
        value={projectId ?? ""}
        onChange={(e) => change(e.target.value)}
      >
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.code} — {name(p.name_en, p.name_ar)}
          </option>
        ))}
      </select>
    </label>
  );
}
