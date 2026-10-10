"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { StepDialog } from "@/components/access/common";
import { PossibleIdHint } from "@/components/common/api-warnings";
import { FormField } from "@/components/common/form-field";
import { useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useFuRefresh } from "@/lib/api/followup";
import { useProjectSettings } from "@/lib/api/queries";
import { DEFAULT_TIME_ZONE, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { Choices, FilePick, toFileInput } from "./common";

type S = Schemas;
type Req = S["FuRequirementRead"];

const CHANNELS: S["FuChannel"][] = ["portal", "email", "hand_delivered", "courier", "phone_radio", "meeting"];
const VERBAL_ONLY: S["FuChannel"][] = ["phone_radio", "meeting"];
const WAIVERS: S["FuWaiverReason"][] = ["not_covered_by_gosi", "body_confirmed_not_required", "reported_by_other_party"];

function useTz(pid: string) {
  const s = useProjectSettings(pid);
  return s.data?.timezone ?? DEFAULT_TIME_ZONE;
}

/* ───────────── generate (or regenerate) a pack: PK-1…PK-5 ───────────── */

export function GeneratePackDialog({ req, onClose }: { req: Req; onClose: () => void }) {
  const t = useTranslations("fu.packDialog");
  const te = useTranslations("enums");
  const refresh = useFuRefresh();
  const router = useRouter();
  const client = req.body === "client";
  const [langs, setLangs] = useState<string[]>(client ? ["en", "ar"] : []);
  return (
    <StepDialog
      title={t("title", { form: req.form_code ? te(`fuForm.${req.form_code}`) : "" })}
      description={t("body")}
      confirmLabel={t("confirm")}
      testId="pack-generate-confirm"
      onConfirm={async () => {
        const pk = await unwrap(
          api.POST("/api/v1/notification-requirements/{requirement_id}/packs", {
            params: { path: { requirement_id: req.id } },
            body: client ? { languages: langs } : {},
          }),
        );
        await refresh();
        toast.success(t("done", { no: pk.pack_no }));
        router.push(`/notification-packs/${pk.id}`);
      }}
      onClose={onClose}
    >
      {req.pack_no && req.pack_status !== "superseded" ? <Alert tone="warning">{t("supersedes", { no: req.pack_no })}</Alert> : null}
      {client ? (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">{t("languages")}</legend>
          <Choices
            label={t("languages")}
            testId="pack-langs"
            value={langs.length === 2 ? "both" : (langs[0] as "en" | "ar" | undefined) ?? ""}
            options={[
              { value: "both", label: t("both") },
              { value: "en", label: t("en") },
              { value: "ar", label: t("ar") },
            ]}
            onChange={(v) => setLangs(v === "both" ? ["en", "ar"] : [v])}
          />
          <p className="text-xs text-muted-foreground">{t("clientDeidentified")}</p>
        </fieldset>
      ) : (
        <p className="text-sm text-muted-foreground">{t("government")}</p>
      )}
    </StepDialog>
  );
}

/* ───────────── record a submission with evidence: SB-1…SB-3 ───────────── */

export function SubmissionDialog({ req, onClose }: { req: Req; onClose: () => void }) {
  const t = useTranslations("fu.submit");
  const te = useTranslations("enums");
  const refresh = useFuRefresh();
  const tz = useTz(req.project_id);
  const verbal = req.stage === "verbal";
  const approvedPack = req.pack_id && req.pack_status === "approved" ? req.pack_id : null;
  const [channel, setChannel] = useState<S["FuChannel"] | "">(verbal ? "phone_radio" : approvedPack ? "portal" : "");
  const [at, setAt] = useState(utcToZonedInput(new Date().toISOString(), tz));
  const [desk, setDesk] = useState("");
  const [refNo, setRefNo] = useState("");
  const [note, setNote] = useState("");
  const [evidence, setEvidence] = useState<File[]>([]);
  const [stamped, setStamped] = useState<File[]>([]);
  const [external, setExternal] = useState<File[]>([]);
  const needsDoc = !verbal && !approvedPack;
  const missing = [
    !channel ? t("needChannel") : null,
    verbal && !desk.trim() ? t("needDesk") : null,
    verbal && !refNo.trim() && !note.trim() ? t("needRefOrNote") : null,
    !verbal && !refNo.trim() && evidence.length === 0 ? t("needEvidence") : null,
    channel === "hand_delivered" && stamped.length === 0 ? t("needStamped") : null,
    needsDoc && external.length === 0 ? t("needDocument") : null,
  ].filter((x): x is string => Boolean(x));
  return (
    <StepDialog
      title={t("title", { body: te(`externalBody.${req.body}`), stage: te(`fuStage.${req.stage}`) })}
      description={t("body")}
      confirmLabel={t("confirm")}
      testId="sub-confirm"
      wide
      disabled={missing.length > 0 || !at}
      onConfirm={async () => {
        const body: S["FuSubmissionCreate"] = {
          channel: channel as S["FuChannel"],
          submitted_at: zonedInputToUtc(at, tz),
          pack_id: approvedPack,
          contacted_desk_en: desk.trim() || null,
          reference_no: refNo.trim() || null,
          call_note: note.trim() || null,
          evidence_files: await Promise.all(evidence.map(toFileInput)),
          stamped_copy: stamped[0] ? await toFileInput(stamped[0]) : null,
          external_document: external[0] ? await toFileInput(external[0]) : null,
        };
        const s = await unwrap(api.POST("/api/v1/notification-requirements/{requirement_id}/submissions", { params: { path: { requirement_id: req.id } }, body }));
        await refresh();
        toast.success(t("done", { no: s.submission_no }));
      }}
      onClose={onClose}
    >
      {approvedPack ? <Alert tone="info">{t("withPack", { no: req.pack_no ?? "" })}</Alert> : null}
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 text-sm font-medium">{t("channel")}</legend>
        <Choices
          label={t("channel")}
          testId="sub-channel"
          value={channel}
          options={CHANNELS.filter((c) => verbal || !VERBAL_ONLY.includes(c)).map((c) => ({ value: c, label: te(`fuChannel.${c}`) }))}
          onChange={setChannel}
        />
      </fieldset>
      <FormField id="sub-at" label={t("submittedAt")} required hint={t("submittedAtHint")}>
        <Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} data-testid="sub-at" />
      </FormField>
      {verbal ? (
        <FormField id="sub-desk" label={t("desk")} required hint={t("deskHint")}>
          <Input value={desk} onChange={(e) => setDesk(e.target.value)} maxLength={120} data-testid="sub-desk" />
        </FormField>
      ) : null}
      <FormField id="sub-ref" label={t("reference")} hint={verbal ? t("refHintVerbal") : t("refHint")}>
        <Input value={refNo} onChange={(e) => setRefNo(e.target.value)} maxLength={60} className="ltr" data-testid="sub-ref" />
      </FormField>
      {verbal ? (
        <FormField id="sub-note" label={t("callNote")}>
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} data-testid="sub-note" />
        </FormField>
      ) : (
        <FormField id="sub-evidence" label={t("evidence")} hint={t("evidenceHint")}>
          <FilePick files={evidence} onChange={setEvidence} max={5} testId="sub-evidence" />
        </FormField>
      )}
      {channel === "hand_delivered" ? (
        <FormField id="sub-stamped" label={t("stamped")} required>
          <FilePick files={stamped} onChange={setStamped} testId="sub-stamped" />
        </FormField>
      ) : null}
      {needsDoc ? (
        <FormField id="sub-external" label={t("external")} required hint={t("externalHint")}>
          <FilePick files={external} onChange={setExternal} testId="sub-external" />
        </FormField>
      ) : null}
      {missing.length ? (
        <ul className="flex flex-col gap-1 rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground" data-testid="sub-missing">
          {missing.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      ) : null}
      <PossibleIdHint text={note} />
    </StepDialog>
  );
}

/* ───────────── body's acknowledgement ───────────── */

export function AckDialog({ sub, projectId, onClose }: { sub: S["FuSubmissionRead"]; projectId: string; onClose: () => void }) {
  const t = useTranslations("fu.ack");
  const refresh = useFuRefresh();
  const tz = useTz(projectId);
  const [at, setAt] = useState(utcToZonedInput(new Date().toISOString(), tz));
  const [refNo, setRefNo] = useState("");
  const [file, setFile] = useState<File[]>([]);
  return (
    <StepDialog
      title={t("title", { no: sub.submission_no })}
      confirmLabel={t("confirm")}
      testId="ack-confirm"
      disabled={!at}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/notification-submissions/{submission_id}/acknowledge", {
            params: { path: { submission_id: sub.id } },
            body: { acknowledged_at: zonedInputToUtc(at, tz), ack_reference: refNo.trim() || null, ack_file: file[0] ? await toFileInput(file[0]) : null },
          }),
        );
        await refresh();
        toast.success(t("done"));
      }}
      onClose={onClose}
    >
      <FormField id="ack-at" label={t("at")} required>
        <Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} data-testid="ack-at" />
      </FormField>
      <FormField id="ack-ref" label={t("reference")}>
        <Input value={refNo} onChange={(e) => setRefNo(e.target.value)} maxLength={60} className="ltr" data-testid="ack-ref" />
      </FormField>
      <FormField id="ack-file" label={t("file")}>
        <FilePick files={file} onChange={setFile} testId="ack-file" />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── reason dialogs: void a submission (217), waive a requirement (218) ───────────── */

export function VoidSubmissionDialog({ sub, onClose }: { sub: S["FuSubmissionRead"]; onClose: () => void }) {
  const t = useTranslations("fu.void");
  const tc = useTranslations("fu.common");
  const refresh = useFuRefresh();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={t("title", { no: sub.submission_no })}
      description={t("body")}
      confirmLabel={t("confirm")}
      destructive
      dismissLabel={tc("back")}
      testId="void-confirm"
      disabled={reason.trim().length < 20}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/notification-submissions/{submission_id}/void", { params: { path: { submission_id: sub.id } }, body: { reason: reason.trim() } }));
        await refresh();
        toast.success(t("done"));
      }}
      onClose={onClose}
    >
      <FormField id="void-reason" label={tc("reason")} required hint={tc("reasonMin", { min: 20, n: reason.trim().length })}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="void-reason" />
      </FormField>
    </StepDialog>
  );
}

export function WaiveDialog({ req, onClose }: { req: Req; onClose: () => void }) {
  const t = useTranslations("fu.waive");
  const tc = useTranslations("fu.common");
  const te = useTranslations("enums");
  const refresh = useFuRefresh();
  const [code, setCode] = useState<S["FuWaiverReason"] | "">("");
  const [text, setText] = useState("");
  const [refNo, setRefNo] = useState("");
  const [file, setFile] = useState<File[]>([]);
  const needFile = code === "body_confirmed_not_required" || code === "reported_by_other_party";
  const needRef = code === "reported_by_other_party";
  return (
    <StepDialog
      title={t("title", { rule: req.rule_code })}
      description={t("body")}
      confirmLabel={t("confirm")}
      destructive
      dismissLabel={tc("back")}
      testId="waive-confirm"
      disabled={!code || text.trim().length < 20}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/notification-requirements/{requirement_id}/waive", {
            params: { path: { requirement_id: req.id } },
            body: { reason_code: code as S["FuWaiverReason"], text: text.trim(), reference: refNo.trim() || null, evidence_file: file[0] ? await toFileInput(file[0]) : null },
          }),
        );
        await refresh();
        toast.success(t("done"));
      }}
      onClose={onClose}
    >
      <FormField id="waive-code" label={t("reason")} required>
        <Select value={code} onChange={(e) => setCode(e.target.value as S["FuWaiverReason"])} data-testid="waive-code">
          <option value="">—</option>
          {WAIVERS.map((w) => (
            <option key={w} value={w}>
              {te(`fuWaiverReason.${w}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="waive-text" label={t("text")} required hint={tc("reasonMin", { min: 20, n: text.trim().length })}>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={500} data-testid="waive-text" />
      </FormField>
      {needRef ? (
        <FormField id="waive-ref" label={t("otherRef")} required>
          <Input value={refNo} onChange={(e) => setRefNo(e.target.value)} maxLength={60} className="ltr" data-testid="waive-ref" />
        </FormField>
      ) : null}
      {needFile ? (
        <FormField id="waive-file" label={t("evidence")} required>
          <FilePick files={file} onChange={setFile} testId="waive-file" />
        </FormField>
      ) : null}
    </StepDialog>
  );
}
