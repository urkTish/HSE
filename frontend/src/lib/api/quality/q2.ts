"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../client";
import type { QueryOf } from "../queries";

/** Query hooks of Quality package Q2 (spec 8-quality Part C). Keys start with `q-` so every Quality write refreshes them. */
type Opt = { enabled?: boolean };
const on = (id: string, o: Opt = {}) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });
const list = { placeholderData: keepPreviousData, retry: false } as const;

export const q2k = {
  mars: (pid: string, q: object) => ["q-mars", pid, q] as const,
  mar: (id: string) => ["q-mar", id] as const,
  mirs: (pid: string, q: object) => ["q-mirs", pid, q] as const,
  mir: (id: string) => ["q-mir", id] as const,
  quarantine: (pid: string, q: object) => ["q-quarantine", pid, q] as const,
  quarantineItem: (id: string) => ["q-quarantine-item", id] as const,
  testTypes: (q: object) => ["q-test-types", q] as const,
  tests: (pid: string, q: object) => ["q-tests", pid, q] as const,
  test: (id: string) => ["q-test", id] as const,
  calendar: (pid: string) => ["q-specimen-calendar", pid] as const,
  pours: (pid: string, q: object) => ["q-pours", pid, q] as const,
  pour: (id: string) => ["q-pour", id] as const,
  wps: (pid: string) => ["q-wps", pid] as const,
  pqrs: (pid: string) => ["q-pqrs", pid] as const,
  welders: (pid: string) => ["q-welders", pid] as const,
  wpqs: (pid: string) => ["q-wpqs", pid] as const,
  welds: (pid: string, q: object) => ["q-welds", pid, q] as const,
  weld: (id: string) => ["q-weld", id] as const,
  lots: (pid: string) => ["q-weld-lots", pid] as const,
  lot: (pid: string, code: string) => ["q-weld-lot", pid, code] as const,
  rates: (pid: string) => ["q-weld-rates", pid] as const,
  continuity: (pid: string) => ["q-welder-continuity", pid] as const,
  calibrations: (pid: string, q: object) => ["q-calibrations", pid, q] as const,
  mteCalibrations: (id: string) => ["q-mte-calibrations", id] as const,
  calibration: (id: string) => ["q-calibration", id] as const,
  label: (id: string) => ["q-mte-label", id] as const,
  oots: (pid: string, q: object) => ["q-oot-reviews", pid, q] as const,
  oot: (id: string) => ["q-oot-review", id] as const,
  competence: () => ["q-competence-reqs"] as const,
  matrix: (pid: string) => ["q-competence-matrix", pid] as const,
};

export function useQMars(pid: string, q: QueryOf<"q_list_mars"> = {}) {
  return useQuery({ queryKey: q2k.mars(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/mars", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQMar(id: string) {
  return useQuery({ queryKey: q2k.mar(id), queryFn: () => unwrap(api.GET("/api/v1/quality/mars/{mar_id}", { params: { path: { mar_id: id } } })), enabled: on(id), retry: false });
}
export function useQMirs(pid: string, q: QueryOf<"q_list_mirs"> = {}) {
  return useQuery({ queryKey: q2k.mirs(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/mirs", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQMir(id: string) {
  return useQuery({ queryKey: q2k.mir(id), queryFn: () => unwrap(api.GET("/api/v1/quality/mirs/{mir_id}", { params: { path: { mir_id: id } } })), enabled: on(id), retry: false });
}
export function useQQuarantine(pid: string, q: QueryOf<"q_list_quarantine"> = {}) {
  return useQuery({ queryKey: q2k.quarantine(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/quarantine", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQQuarantineItem(id: string) {
  return useQuery({ queryKey: q2k.quarantineItem(id), queryFn: () => unwrap(api.GET("/api/v1/quality/quarantine/{item_id}", { params: { path: { item_id: id } } })), enabled: on(id), retry: false });
}
export function useQTestTypes(q: QueryOf<"q_list_test_types"> = {}) {
  return useQuery({ queryKey: q2k.testTypes(q), queryFn: () => unwrap(api.GET("/api/v1/quality/test-types", { params: { query: q } })), staleTime: 60_000, retry: false });
}
export function useQTests(pid: string, q: QueryOf<"q_list_tests"> = {}) {
  return useQuery({ queryKey: q2k.tests(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/tests", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQTest(id: string) {
  return useQuery({ queryKey: q2k.test(id), queryFn: () => unwrap(api.GET("/api/v1/quality/tests/{test_id}", { params: { path: { test_id: id } } })), enabled: on(id), retry: false });
}
export function useQSpecimenCalendar(pid: string) {
  return useQuery({ queryKey: q2k.calendar(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/specimen-calendar", { params: P(pid) })), enabled: on(pid), retry: false });
}
export function useQPours(pid: string, q: QueryOf<"q_list_pours"> = {}) {
  return useQuery({ queryKey: q2k.pours(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/pours", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQPour(id: string) {
  return useQuery({ queryKey: q2k.pour(id), queryFn: () => unwrap(api.GET("/api/v1/quality/pours/{pour_id}", { params: { path: { pour_id: id } } })), enabled: on(id), retry: false });
}
export function useQWps(pid: string) {
  return useQuery({ queryKey: q2k.wps(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/wps", { params: P(pid) })), enabled: on(pid), retry: false });
}
export function useQPqrs(pid: string) {
  return useQuery({ queryKey: q2k.pqrs(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/pqrs", { params: P(pid) })), enabled: on(pid), retry: false });
}
export function useQWelders(pid: string) {
  return useQuery({ queryKey: q2k.welders(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/welders", { params: P(pid) })), enabled: on(pid), retry: false });
}
export function useQWpqs(pid: string) {
  return useQuery({ queryKey: q2k.wpqs(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/wpqs", { params: P(pid) })), enabled: on(pid), retry: false });
}
export function useQWelds(pid: string, q: QueryOf<"q_list_welds"> = {}) {
  return useQuery({ queryKey: q2k.welds(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/welds", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQWeld(id: string) {
  return useQuery({ queryKey: q2k.weld(id), queryFn: () => unwrap(api.GET("/api/v1/quality/welds/{weld_id}", { params: { path: { weld_id: id } } })), enabled: on(id), retry: false });
}
export function useQWeldLots(pid: string) {
  return useQuery({ queryKey: q2k.lots(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/weld-lots", { params: P(pid) })), enabled: on(pid), retry: false });
}
export function useQWeldLot(pid: string, code: string) {
  return useQuery({
    queryKey: q2k.lot(pid, code),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/weld-lots/{lot_code}", { params: { path: { project_id: pid, lot_code: code } } })),
    enabled: on(pid) && Boolean(code),
    retry: false,
  });
}
export function useQRepairRates(pid: string) {
  return useQuery({ queryKey: q2k.rates(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/weld-repair-rates", { params: P(pid) })), enabled: on(pid), retry: false });
}
export function useQContinuity(pid: string) {
  return useQuery({ queryKey: q2k.continuity(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/welder-continuity", { params: P(pid) })), enabled: on(pid), retry: false });
}
export function useQCalibrations(pid: string, q: QueryOf<"q_list_calibrations"> = {}) {
  return useQuery({ queryKey: q2k.calibrations(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/calibrations", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQMteCalibrations(id: string) {
  return useQuery({ queryKey: q2k.mteCalibrations(id), queryFn: () => unwrap(api.GET("/api/v1/quality/mte/{mte_id}/calibrations", { params: { path: { mte_id: id } } })), enabled: on(id), retry: false });
}
export function useQCalibration(id: string) {
  return useQuery({ queryKey: q2k.calibration(id), queryFn: () => unwrap(api.GET("/api/v1/quality/calibrations/{cal_id}", { params: { path: { cal_id: id } } })), enabled: on(id), retry: false });
}
export function useQMteLabel(id: string) {
  return useQuery({ queryKey: q2k.label(id), queryFn: () => unwrap(api.GET("/api/v1/quality/mte/{mte_id}/label", { params: { path: { mte_id: id } } })), enabled: on(id), retry: false });
}
export function useQOotReviews(pid: string, q: QueryOf<"q_list_oot"> = {}) {
  return useQuery({ queryKey: q2k.oots(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/oot-reviews", { params: { ...P(pid), query: q } })), enabled: on(pid), retry: false });
}
export function useQOotReview(id: string) {
  return useQuery({ queryKey: q2k.oot(id), queryFn: () => unwrap(api.GET("/api/v1/quality/oot-reviews/{review_id}", { params: { path: { review_id: id } } })), enabled: on(id), retry: false });
}
export function useQCompetenceReqs() {
  return useQuery({ queryKey: q2k.competence(), queryFn: () => unwrap(api.GET("/api/v1/quality/competence/requirements")), retry: false });
}
export function useQCompetenceMatrix(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: q2k.matrix(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/competence/matrix", { params: P(pid) })), enabled: on(pid, o), retry: false });
}
