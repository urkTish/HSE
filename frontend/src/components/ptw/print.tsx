"use client";
import { Printer } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { AccessPrintHeader, BiLabel, QrImage, useBi } from "@/components/access/common";
import { ErrorState, LoadingState } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useClosurePack, usePermitPrint } from "@/lib/api/ptw";
import { useFormatters } from "@/lib/use-formatters";
import { useProjectId } from "./common";

type S = Schemas;
type Print = S["PermitPrintRead"];

function Bi({ en, ar }: { en: ReactNode; ar: ReactNode }) {
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1.5">
      <span lang="en" dir="ltr">
        {en}
      </span>
      <span aria-hidden>/</span>
      <span lang="ar" dir="rtl">
        {ar}
      </span>
    </span>
  );
}

function hhmm(t: string): string {
  return t.slice(0, 5);
}

/** The A4 body shared by the permit print and the closed-permit pack. */
function PermitSheet({ p, title, children }: { p: Print; title: "ptwTitle" | "ptwClosureTitle"; children?: ReactNode }) {
  const t = useTranslations("ptwPrint");
  const te = useTranslations("enums");
  const pid = useProjectId();
  const { dateTime } = useFormatters(pid);
  const bi = useBi();
  return (
    <article className="paper mx-auto flex w-full max-w-3xl flex-col gap-4 rounded-xl border bg-white p-6 text-black print:max-w-none print:rounded-none print:border-0 print:p-0" data-testid="permit-print">
      <AccessPrintHeader title={title} />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <p className="ltr text-2xl font-bold tracking-wide" data-testid="print-permit-no">
            {p.display_no}
          </p>
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <BiLabel k="status" className="text-xs" />
            <span className="rounded border-2 border-black px-2 py-0.5 text-base font-bold">{te(`permitStatus.${p.status}`)}</span>
            {p.current_shift_no ? (
              <span className="text-sm">
                <BiLabel k="ptwShift" className="text-xs" /> <span className="font-semibold tabular-nums">{p.current_shift_no}</span>
              </span>
            ) : null}
          </p>
          <p className="flex flex-col text-sm">
            <BiLabel k="ptwTypes" className="text-xs" />
            <span className="font-semibold">{p.work_types.map((w) => te(`permitType.${w}`)).join(" · ")}</span>
          </p>
          <p className="flex flex-col text-sm">
            <BiLabel k="dates" className="text-xs" />
            <span className="ltr text-lg font-semibold">
              {dateTime(p.valid_from_at)} – {dateTime(p.valid_to_at)}
            </span>
          </p>
        </div>
        <div className="flex flex-col items-center gap-1 rounded-lg border-2 border-black p-2" data-testid="print-qr" data-payload={p.qr_payload}>
          <QrImage payload={p.qr_payload} size={150} label={t("qr", { no: p.display_no })} />
          <span className="ltr font-mono font-bold" data-testid="print-ref">
            {p.printed_ref}
          </span>
          <BiLabel k="ptwScan" className="text-[8pt]" />
        </div>
      </div>
      <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-6 gap-y-2 border-y border-black py-3 text-sm">
        <dt>
          <BiLabel k="zones" stack className="text-xs font-medium" />
        </dt>
        <dd className="ltr">{p.zones.join(", ")}</dd>
        <dt>
          <BiLabel k="ptwLocation" stack className="text-xs font-medium" />
        </dt>
        <dd>{p.location}</dd>
        <dt>
          <BiLabel k="windows" stack className="text-xs font-medium" />
        </dt>
        <dd className="ltr tabular-nums">{p.windows.map((w) => `${hhmm(w.start_local)}–${hhmm(w.end_local)}`).join(" · ")}</dd>
        <dt>
          <BiLabel k="ptwReceiver" stack className="text-xs font-medium" />
        </dt>
        <dd>{p.receiver_name}</dd>
        <dt>
          <BiLabel k="ptwIssuer" stack className="text-xs font-medium" />
        </dt>
        <dd>{p.issuer_name ?? "—"}</dd>
        <dt>
          <BiLabel k="ptwAreaAuthority" stack className="text-xs font-medium" />
        </dt>
        <dd>{p.area_authority_name ?? "—"}</dd>
      </dl>
      <section>
        <h2 className="mb-2 flex items-baseline gap-2 font-semibold">
          <BiLabel k="crew" />
          <span className="tabular-nums">({p.crew.length})</span>
        </h2>
        <table className="w-full text-sm" data-testid="print-crew">
          <thead>
            <tr className="border-b-2 border-black text-xs">
              <th className="py-1 text-start font-medium">
                <BiLabel k="workerNo" stack />
              </th>
              <th className="py-1 text-start font-medium">
                <BiLabel k="name" stack />
              </th>
              <th className="py-1 text-start font-medium">
                <BiLabel k="role" stack />
              </th>
            </tr>
          </thead>
          <tbody>
            {p.crew.map((c, i) => (
              <tr key={i} className="border-b">
                <td className="ltr py-1 font-mono">{c.worker_no ?? "—"}</td>
                <td className="py-1">{c.name_en || c.name_ar ? <Bi en={c.name_en ?? ""} ar={c.name_ar ?? c.name_en ?? ""} /> : "—"}</td>
                <td className="py-1">{te(`ptwCrewRole.${c.crew_role}`)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="grid gap-4 sm:grid-cols-2 print:grid-cols-2">
        <div>
          <h2 className="mb-1 font-semibold">
            <BiLabel k="ptwGas" />
          </h2>
          {p.latest_gas_test ? (
            <p className="text-sm" data-testid="print-gas">
              <span className="ltr font-mono">{p.latest_gas_test.test_no}</span> · <span className="ltr">{dateTime(p.latest_gas_test.tested_at)}</span> · <span className="font-semibold uppercase">{p.latest_gas_test.result}</span>
            </p>
          ) : (
            <p className="text-sm">—</p>
          )}
        </div>
        <div>
          <h2 className="mb-1 font-semibold">
            <BiLabel k="ptwIsolations" />
          </h2>
          {p.isolations.length ? (
            <ul className="ltr text-sm" data-testid="print-isolations">
              {p.isolations.map((x, i) => (
                <li key={i} className="font-mono">
                  {x.iso_no} #{x.point_no} {x.device_tag} · {bi("ptwLock").en} {x.lock_no ?? "—"} · {bi("ptwTag").en} {x.tag_no ?? "—"}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm">—</p>
          )}
        </div>
      </section>
      <section>
        <h2 className="mb-1 font-semibold">
          <BiLabel k="ptwConditions" />
        </h2>
        {p.key_conditions.length ? (
          <ul className="list-disc ps-5 text-sm">
            {p.key_conditions.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm">—</p>
        )}
      </section>
      <section className="rounded border-2 border-black p-2">
        <h2 className="mb-1 font-semibold">
          <BiLabel k="ptwEmergency" />
        </h2>
        <p className="text-sm whitespace-pre-line">{p.emergency_info}</p>
      </section>
      {children}
      <footer className="mt-auto flex flex-col gap-1 border-t-2 border-black pt-2 text-xs">
        <BiLabel k="ptwFooter" stack className="gap-1" />
        <span className="flex flex-wrap items-baseline gap-x-1 text-[8pt]" data-testid="audit-hash">
          <span>{bi("ptwHash").en}</span> / <bdi dir="rtl">{bi("ptwHash").ar}</bdi>:{" "}
          <bdi dir="ltr" className="font-mono break-all">{p.audit_hash}</bdi> · <bdi dir="ltr">{dateTime(p.generated_at)}</bdi>
        </span>
      </footer>
    </article>
  );
}

function PrintToolbar({ id }: { id: string }) {
  const tc = useTranslations("common");
  return (
    <div className="flex gap-2 print:hidden">
      <Button onClick={() => window.print()} data-testid="do-print">
        <Printer aria-hidden />
        {tc("print")}
      </Button>
      <Button variant="outline" asChild>
        <Link href={`/permits/${id}`}>{tc("back")}</Link>
      </Button>
    </div>
  );
}

export function PermitPrint({ id }: { id: string }) {
  const q = usePermitPrint(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return (
    <div className="flex flex-col gap-4">
      <PrintToolbar id={id} />
      <PermitSheet p={q.data} title="ptwTitle" />
    </div>
  );
}

/** Closed-permit pack: the permit sheet plus shifts, suspensions, gas tests, signatures and the closure checklist. */
export function ClosurePack({ id }: { id: string }) {
  const te = useTranslations("enums");
  const pid = useProjectId();
  const { dateTime } = useFormatters(pid);
  const q = useClosurePack(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const c = q.data;
  return (
    <div className="flex flex-col gap-4">
      <PrintToolbar id={id} />
      <PermitSheet p={c} title="ptwClosureTitle">
        <section data-testid="pack-shifts">
          <h2 className="mb-1 font-semibold">
            <BiLabel k="ptwShifts" />
          </h2>
          <ul className="text-sm">
            {c.shifts.map((s) => (
              <li key={s.id} className="ltr">
                #{s.shift_no} {dateTime(s.started_at)} – {s.ended_at ? dateTime(s.ended_at) : "…"} · {s.receiver.full_name_en} / {s.issuer.full_name_en} · {s.crew_present_count}
              </li>
            ))}
          </ul>
        </section>
        {c.suspensions.length ? (
          <section>
            <h2 className="mb-1 font-semibold">
              <BiLabel k="ptwSuspensions" />
            </h2>
            <ul className="text-sm">
              {c.suspensions.map((s) => (
                <li key={s.id}>
                  <span className="ltr">{dateTime(s.suspended_at)}</span> · {te(`statusReason.${s.reason}`)}
                  {s.resumed_at ? (
                    <>
                      {" "}
                      → <span className="ltr">{dateTime(s.resumed_at)}</span>
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <section>
          <h2 className="mb-1 font-semibold">
            <BiLabel k="ptwGasTests" />
          </h2>
          <ul className="ltr text-sm">
            {c.gas_tests.length ? c.gas_tests.map((g) => <li key={g.id} className="font-mono">{g.test_no} · {dateTime(g.tested_at)} · {g.result}</li>) : <li>—</li>}
          </ul>
        </section>
        <section>
          <h2 className="mb-1 font-semibold">
            <BiLabel k="ptwSignatures" />
          </h2>
          <ul className="text-sm" data-testid="pack-signatures">
            {c.signatures.map((s) => (
              <li key={s.id}>
                {te(`signaturePurpose.${s.purpose}`)} · {s.user?.full_name_en ?? s.worker_label ?? "—"} ({s.role_label}) · <span className="ltr">{dateTime(s.signed_at)}</span> · <span className="ltr font-mono text-[8pt]">#{s.permit_hash.slice(0, 12)}</span>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h2 className="mb-1 font-semibold">
            <BiLabel k="ptwClosureChecklist" />
          </h2>
          <ul className="text-sm">
            {c.closure_checklist.items.map((i) => (
              <li key={i.code}>
                <span className="ltr font-mono text-xs">{i.code}</span> <Bi en={i.label_en} ar={i.label_ar} /> — <span className="font-semibold">{i.answer ? te(`checklistAnswer.${i.answer === "n.a." ? "na" : i.answer}` as "checklistAnswer.yes") : "—"}</span>
              </li>
            ))}
          </ul>
          {c.closed_at ? (
            <p className="mt-1 text-sm">
              <BiLabel k="ptwClosedAt" className="text-xs" /> <span className="ltr font-semibold">{dateTime(c.closed_at)}</span>
            </p>
          ) : null}
        </section>
      </PermitSheet>
    </div>
  );
}
