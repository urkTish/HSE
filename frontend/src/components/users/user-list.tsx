"use client";
import { UserPlus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { PageHeader } from "@/components/common/page-header";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { ExportButtons } from "@/components/common/export-buttons";
import { useMeData } from "@/components/shell/me-context";
import { Link } from "@/i18n/navigation";
import { useUsers, type QueryOf } from "@/lib/api/queries";
import type { Schemas } from "@/lib/api/client";
import { EMPLOYER_TYPES, ROLES, USER_STATUSES } from "@/lib/enums";
import { useCurrentProject } from "@/lib/current-project";
import { can } from "@/lib/permissions";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";

type Sort = NonNullable<QueryOf<"list_users">["sort"]>;
const SORTS: Sort[] = ["name", "-name", "email", "-email", "last_login_at", "-last_login_at"];
const PAGE_SIZE = 25;

export function UserList() {
  const t = useTranslations("user");
  const tr = useTranslations("role");
  const tc = useTranslations("common");
  const ts = useTranslations("shell");
  const me = useMeData();
  const name = useLocalizedName();
  const { dateTime } = useFormatters();
  const { projects } = useCurrentProject();
  const projectCode = new Map(projects.map((p) => [p.id, p.code]));
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<Schemas["UserStatus"] | "">("");
  const [role, setRole] = useState<Schemas["Role"] | "">("");
  const [projectId, setProjectId] = useState("");
  const [employer, setEmployer] = useState<Schemas["EmployerType"] | "">("");
  const [sort, setSort] = useState<Sort>("name");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const query = useUsers({
    q: dq || undefined,
    status: status ? [status] : undefined,
    role: role || undefined,
    project_id: projectId || undefined,
    employer_type: employer || undefined,
    sort,
    page,
    page_size: PAGE_SIZE,
  });
  const reset = () => setPage(1);

  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          can(me, "user.invite") ? (
            <Button asChild>
              <Link href="/users/invite" data-testid="invite-user">
                <UserPlus aria-hidden />
                {t("invite")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar actions={can(me, "export.lists") ? <ExportButtons dataset="users" params={{ q: dq, status, project_id: projectId }} /> : null}>
        <SearchFilter id="user-q" value={q} onChange={(v) => { setQ(v); reset(); }} />
        <SelectFilter id="user-status" label={t("fields.status")} value={status} onChange={(v) => { setStatus(v); reset(); }} options={USER_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))} />
        <SelectFilter id="user-role" label={t("fields.roles")} value={role} onChange={(v) => { setRole(v); reset(); }} options={ROLES.map((r) => ({ value: r, label: tr(r) }))} allLabel={t("anyRole")} />
        <SelectFilter id="user-project" label={ts("projectSwitcher")} value={projectId} onChange={(v) => { setProjectId(v); reset(); }} options={projects.map((p) => ({ value: p.id, label: p.code }))} />
        <SelectFilter id="user-employer" label={t("fields.employer_type")} value={employer} onChange={(v) => { setEmployer(v); reset(); }} options={EMPLOYER_TYPES.map((e) => ({ value: e, label: t(`employerType.${e}`) }))} />
        <SelectFilter id="user-sort" label={tc("sortBy")} value={sort} onChange={(v) => setSort(v || "name")} options={SORTS.map((s) => ({ value: s, label: t(`sort.${s}`) }))} allLabel={t("sort.name")} />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : query.data && query.data.items.length > 0 ? (
        <>
          <Table data-testid="users-table">
            <THead>
              <TR>
                <TH>{t("fields.name")}</TH>
                <TH>{t("fields.email")}</TH>
                <TH>{t("fields.employer_type")}</TH>
                <TH>{t("fields.roles")}</TH>
                <TH>{t("fields.last_login_at")}</TH>
                <TH>{t("fields.status")}</TH>
              </TR>
            </THead>
            <TBody>
              {query.data.items.map((u) => (
                <TR key={u.id} data-testid="user-row">
                  <TD>
                    <Link href={`/users/${u.id}`} className="font-medium text-primary hover:underline">
                      {name(u.full_name_en, u.full_name_ar)}
                    </Link>
                  </TD>
                  <TD className="ltr">{u.email ?? <span className="text-muted-foreground">{t("contactHidden")}</span>}</TD>
                  <TD>{t(`employerType.${u.employer_type}`)}</TD>
                  <TD>
                    <ul className="flex flex-col gap-0.5 text-xs">
                      {u.role_assignments
                        .filter((a) => a.is_active)
                        .map((a) => (
                          <li key={a.id}>
                            {tr(a.role)}
                            {a.project_id ? <span className="text-muted-foreground ltr"> · {projectCode.get(a.project_id) ?? "…"}</span> : null}
                          </li>
                        ))}
                    </ul>
                  </TD>
                  <TD>{u.last_login_at ? dateTime(u.last_login_at) : t("neverLoggedIn")}</TD>
                  <TD>
                    <StatusBadge status={u.status} label={t(`status.${u.status}`)} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPage={setPage} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}
