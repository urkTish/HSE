import type { Schemas } from "@/lib/api/client";

type S = Schemas;

/** Phase 6a (occupational health) enum values in display order (spec 6a §3, §4). */
export const FITNESS_CATEGORIES = ["general", "task", "surveillance"] as const satisfies readonly S["FitnessCategory"][];
export const EXAMINER_CLASSES = ["occupational_physician", "physician", "nurse"] as const satisfies readonly S["ExaminerClass"][];
export const SIGNING_CLASSES = ["occupational_physician", "physician"] as const satisfies readonly S["ExaminerClass"][];
export const EXAMINER_STATUSES = ["active", "suspended", "withdrawn", "expired"] as const satisfies readonly S["ExaminerStatus"][];
export const MED_PROVIDER_KINDS = ["site_clinic", "external_clinic", "contractor_clinic"] as const satisfies readonly S["MedicalProviderKind"][];
export const MED_PROVIDER_STATUSES = ["draft", "pending_approval", "approved", "suspended", "blacklisted"] as const satisfies readonly S["MedicalProviderStatus"][];
export const MED_BLACKLIST_SCOPES = ["all_records", "issued_from"] as const satisfies readonly S["MedicalBlacklistScope"][];
export const TYPICAL_TESTS = [
  "history_questionnaire",
  "vision_acuity",
  "colour_vision",
  "depth_perception",
  "audiometry",
  "spirometry",
  "chest_xray",
  "cardio_exam",
  "blood_pressure",
  "balance_vertigo_screen",
  "claustrophobia_screen",
  "respirator_questionnaire",
  "blood_count",
  "musculoskeletal_exam",
] as const satisfies readonly S["TypicalTest"][];
export const RESTRICTION_CODES = [
  "no_work_at_height",
  "no_confined_space",
  "no_driving",
  "no_plant_operation",
  "no_respirator_use",
  "no_heat_exposure",
  "no_noise_exposure",
  "no_radiation_work",
  "lifting_limit_kg",
  "no_night_work",
  "no_lone_work",
  "light_duties_only",
  "requires_corrective_lenses",
  "other_functional",
] as const satisfies readonly S["RestrictionCode"][];
export const EXPOSURE_GROUPS = ["noise_85", "silica_rcs", "ionising_radiation", "heat_outdoor"] as const satisfies readonly S["ExposureGroup"][];
export const FITNESS_OUTCOMES = ["fit", "fit_with_restrictions", "temporarily_unfit", "permanently_unfit"] as const satisfies readonly S["FitnessOutcome"][];
export const ASSESSMENT_TYPES = ["pre_placement", "periodic", "return_to_work", "referral", "change_of_task", "post_exposure", "exit"] as const satisfies readonly S["AssessmentType"][];
export const ASSESSMENT_SOURCES = ["site_clinic", "external_certificate", "import"] as const satisfies readonly S["AssessmentSource"][];
export const ASSESSMENT_STATUSES = ["draft", "awaiting_signoff", "submitted", "accepted", "rejected", "revoked"] as const satisfies readonly S["AssessmentStatus"][];
export const MED_VERIFICATION_STATUSES = ["not_verified", "verified", "failed", "unable_to_verify"] as const satisfies readonly S["VerificationStatus"][];
export const FITNESS_VERIF_METHODS = ["clinic_portal", "clinic_email", "clinic_phone"] as const satisfies readonly S["FitnessVerificationMethod"][];
export const FITNESS_VERIF_OUTCOMES = ["confirmed", "not_found", "details_differ", "revoked_by_clinic", "no_response"] as const satisfies readonly S["FitnessVerificationOutcome"][];
export const FITNESS_SCAN_REASONS = ["verification", "authority_request", "gosi_claim", "legal", "other"] as const satisfies readonly S["FitnessScanReason"][];
export const HOLD_STATUSES = ["active", "released", "cancelled"] as const satisfies readonly S["HoldStatus"][];
export const REFERRAL_STATUSES = ["open", "assessed", "cancelled"] as const satisfies readonly S["ReferralStatus"][];
export const REFERRAL_REASONS = [
  "observed_unwell",
  "heat_illness_episode",
  "self_reported",
  "return_after_absence",
  "post_incident_no_injury",
  "certificate_restriction",
  "supervisor_concern",
  "other",
] as const satisfies readonly S["ReferralReason"][];
export const MED_APPLIES_TO_MANUAL = ["all_workers", "trade", "exposure_group", "adp_category", "zone"] as const satisfies readonly S["MedicalAppliesTo"][];
export const MED_IMPORT_SOURCES = ["clinic_register_file", "contractor_file"] as const satisfies readonly S["MedicalImportSource"][];
export const MED_IMPORT_STATUSES = ["uploaded", "validated", "committed", "discarded", "expired"] as const satisfies readonly S["MedicalImportStatus"][];
export const MEDICAL_KPIS = ["K-89", "K-90", "K-91", "K-92", "K-93", "K-94", "K-95", "K-96"] as const satisfies readonly S["KpiMetric"][];
export const MEDICAL_KPI_GROUP_BY = ["code", "code_category", "contractor", "trade", "month", "gap_reason"] as const satisfies readonly S["MedicalKpiGroupBy"][];
/** Restrictions that carry a value (lifting limit in kg) or free text (other functional limit). */
export const RESTRICTION_WITH_VALUE: readonly S["RestrictionCode"][] = ["lifting_limit_kg"];
export const RESTRICTION_WITH_TEXT: readonly S["RestrictionCode"][] = ["other_functional"];
