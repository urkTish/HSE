"use client";
import {
  Trophy,
  MessageCircleWarning,
  FileStack,
  FileDown,
  FireExtinguisher,
  OctagonAlert,
  MessagesSquare,
  FileSearch,
  LifeBuoy,
  Megaphone,
  Droplets,
  FileBarChart,
  Siren,
  Sun,
  Thermometer,
  Activity,
  BookMarked,
  HeartPulse,
  Stethoscope,
  Award,
  BookOpenCheck,
  Grid3x3,
  Library,
  Presentation,
  Ban,
  Forklift,
  Upload,
  Wrench,
  ScanSearch,
  Fence,
  Landmark,
  FileBadge,
  BadgeCheck,
  ClipboardSignature,
  Cog,
  FileCheck2,
  Gauge as GaugeIcon,
  Layers,
  LockKeyhole,
  MonitorPlay,
  UserCheck,
  Wind,
  Bot,
  Car,
  DoorOpen,
  GraduationCap,
  IdCard,
  KanbanSquare,
  Plane,
  RadioTower,
  QrCode,
  ScanLine,
  Shield,
  SquareParking,
  TowerControl,
  Construction,
  Building2,
  CalendarCheck,
  ClipboardCheck,
  ClipboardList,
  Eye,
  FileText,
  Gauge,
  ListChecks,
  ListTree,
  ShieldAlert,
  SlidersHorizontal,
  Timer,
  HardHat,
  Home,
  LayoutGrid,
  MapPinned,
  Network,
  ScrollText,
  Settings,
  UserRound,
  Users,
  Leaf,
  Truck,
  AudioWaveform,
  MessageSquareWarning,
  BellRing,
  Lightbulb,
  MailCheck,
  Repeat2,
} from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { can, type Capability } from "@/lib/permissions";
import { useCurrentProject } from "@/lib/current-project";
import { useMeData } from "@/components/shell/me-context";

interface Item {
  href: string;
  label: string;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
  exact?: boolean;
  testId: string;
}

function NavLink({ item, onNavigate }: { item: Item; onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      data-testid={item.testId}
      className={cn(
        "relative flex min-h-touch items-center gap-3 rounded-md px-3 text-sm text-sidebar-foreground/85 transition-colors hover:bg-sidebar-active hover:text-sidebar-foreground",
        "focus-visible:outline-sidebar-indicator",
        active &&
          "bg-sidebar-active font-semibold text-sidebar-foreground shadow-[inset_0_1px_0_rgb(255_255_255/0.05)] before:absolute before:inset-y-2 before:start-0 before:w-1 before:rounded-full before:bg-sidebar-indicator",
      )}
    >
      {/* Icons are not directional, so they are not mirrored in RTL. */}
      <item.Icon aria-hidden className={cn("size-5 shrink-0", active ? "text-sidebar-indicator" : "text-sidebar-muted")} />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const t = useTranslations("nav");
  const me = useMeData();
  const { project } = useCurrentProject();
  const g = (c: Capability, pid?: string | null) => can(me, c, pid);

  const main: Item[] = [
    { href: "/", label: g("dashboard.view") ? t("dashboard") : t("home"), Icon: g("dashboard.view") ? Gauge : Home, exact: true, testId: "nav-home" },
    ...(g("project.view") ? [{ href: "/projects", label: t("projects"), Icon: Building2, exact: true, testId: "nav-projects" }] : []),
    ...(g("contractor.view") ? [{ href: "/contractors", label: t("contractors"), Icon: HardHat, testId: "nav-contractors" }] : []),
    ...(g("user.view_directory") ? [{ href: "/users", label: t("users"), Icon: Users, testId: "nav-users" }] : []),
    ...(g("audit_log.read") ? [{ href: "/audit-log", label: t("auditLog"), Icon: ScrollText, testId: "nav-audit" }] : []),
    ...(me.is_hse_manager ? [{ href: "/ai-logs", label: t("aiLogs"), Icon: Bot, testId: "nav-ai-logs" }] : []),
    ...(g("hse_settings.edit") ? [{ href: "/reference-lists", label: t("referenceLists"), Icon: ListTree, testId: "nav-reference-lists" }] : []),
  ];
  const pid = project?.id;
  const projectItems: Item[] = pid
    ? [
        { href: `/projects/${pid}`, label: t("overview"), Icon: LayoutGrid, exact: true, testId: "nav-project-overview" },
        ...(g("site_zone.view", pid)
          ? [
              { href: `/projects/${pid}/sites`, label: t("sites"), Icon: MapPinned, testId: "nav-sites" },
              { href: `/projects/${pid}/zones`, label: t("zones"), Icon: ClipboardList, testId: "nav-zones" },
            ]
          : []),
        ...(g("contractor.view", pid)
          ? [{ href: `/projects/${pid}/engagements`, label: t("engagements"), Icon: Network, testId: "nav-engagements" }]
          : []),
        ...(g("settings.view", pid)
          ? [{ href: `/projects/${pid}/settings`, label: t("settings"), Icon: Settings, testId: "nav-settings" }]
          : []),
      ]
    : [];

  const dash = pid ? g("dashboard.view", pid) : false;
  const hseItems: Item[] = pid
    ? [
        ...(g("workforce.view", pid) ? [{ href: "/workforce", label: t("workforce"), Icon: Timer, testId: "nav-workforce" }] : []),
        ...(g("incident.view", pid) ? [{ href: "/incidents", label: t("incidents"), Icon: ShieldAlert, testId: "nav-incidents" }] : []),
        ...(g("observation.create", pid) || dash ? [{ href: "/observations", label: t("observations"), Icon: Eye, testId: "nav-observations" }] : []),
        ...(g("inspection.record", pid) || g("inspection.plan_manage", pid) || dash
          ? [{ href: "/inspections", label: t("inspections"), Icon: ClipboardCheck, testId: "nav-inspections" }]
          : []),
        ...(g("ca.create", pid) || g("ca.update_own", pid) || dash ? [{ href: "/actions", label: t("actions"), Icon: ListChecks, testId: "nav-actions" }] : []),
        ...(dash ? [{ href: "/meetings", label: t("meetings"), Icon: CalendarCheck, testId: "nav-meetings" }] : []),
        ...(g("monthly_report.view", pid) || g("monthly_report.generate", pid)
          ? [{ href: "/reports", label: t("reports"), Icon: FileText, testId: "nav-reports" }]
          : []),
        ...(g("settings.view", pid) ? [{ href: "/hse-settings", label: t("hseSettings"), Icon: SlidersHorizontal, testId: "nav-hse-settings" }] : []),
      ]
    : [];

  const ac = (...cs: Capability[]) => cs.some((c) => g(c, pid));
  const airport = Boolean(project?.is_airport);
  const accessItems: Item[] = pid
    ? [
        ...(ac("worker.view", "worker.edit") ? [{ href: "/workers", label: t("workers"), Icon: IdCard, testId: "nav-workers" }] : []),
        ...(ac("induction.record", "induction.course_manage", "worker.view")
          ? [{ href: "/inductions", label: t("inductions"), Icon: GraduationCap, testId: "nav-inductions" }]
          : []),
        ...(ac("zone_profile.edit", "worker.view") ? [{ href: "/zone-profiles", label: t("zoneProfiles"), Icon: Shield, testId: "nav-zone-profiles" }] : []),
        ...(airport && ac("pass_application.create", "pass_application.endorse", "pass_application.process", "access_works.view")
          ? [{ href: "/pass-applications", label: t("passes"), Icon: BadgeCheck, testId: "nav-passes" }]
          : []),
        ...(airport && ac("adp.apply", "adp.issue", "access_works.view") ? [{ href: "/adps", label: t("adps"), Icon: SquareParking, testId: "nav-adps" }] : []),
        ...(ac("vehicle.edit", "avp.issue", "access_works.view") ? [{ href: "/vehicles", label: t("vehicles"), Icon: Car, testId: "nav-vehicles" }] : []),
        ...(airport && ac("notam.edit", "notam.process", "access_works.view") ? [{ href: "/notams", label: t("notams"), Icon: RadioTower, testId: "nav-notams" }] : []),
        ...(airport && ac("obstacle.edit", "obstacle.decide", "access_works.view")
          ? [{ href: "/obstacle-clearances", label: t("obstacles"), Icon: TowerControl, testId: "nav-obstacles" }]
          : []),
        ...(airport && ac("wap.edit", "wap.approve", "wap.close", "wap.suspend", "access_works.view")
          ? [
              { href: "/waps", label: t("waps"), Icon: Construction, testId: "nav-waps" },
              { href: "/wap-board", label: t("wapBoard"), Icon: KanbanSquare, testId: "nav-wap-board" },
            ]
          : []),
        ...(ac("gate.manage") ? [{ href: "/gates", label: t("gates"), Icon: DoorOpen, testId: "nav-gates" }] : []),
        ...(ac("gate.check") ? [{ href: "/gate", label: t("gateCheck"), Icon: QrCode, testId: "nav-gate-check" }] : []),
        ...(ac("gate_log.view") ? [{ href: "/gate-log", label: t("gateLog"), Icon: ScanLine, testId: "nav-gate-log" }] : []),
        ...(ac("access_settings.edit") ? [{ href: "/access-settings", label: t("accessSettings"), Icon: Plane, testId: "nav-access-settings" }] : []),
      ]
    : [];

  const ptwView = ac("permit.view");
  const ptwItems: Item[] = pid
    ? [
        ...(ptwView ? [{ href: "/permits", label: t("permits"), Icon: FileCheck2, testId: "nav-permits" }] : []),
        ...(ptwView ? [{ href: "/ptw-board", label: t("ptwBoard"), Icon: MonitorPlay, testId: "nav-ptw-board" }] : []),
        ...(ac("permit.view", "gas_test.record", "gas_detector.manage") ? [{ href: "/gas-tests", label: t("gas"), Icon: Wind, testId: "nav-gas" }] : []),
        ...(ac("permit.view", "isolation.manage") ? [{ href: "/isolations", label: t("isolations"), Icon: LockKeyhole, testId: "nav-isolations" }] : []),
        ...(ac("permit.view", "simops.coordinate") ? [{ href: "/simops-conflicts", label: t("simops"), Icon: Layers, testId: "nav-simops" }] : []),
        ...(ac("jsa_template.manage", "permit.prepare", "permit.view") ? [{ href: "/jsa-templates", label: t("jsa"), Icon: ClipboardSignature, testId: "nav-jsa" }] : []),
        ...(ac("ptw_audit.conduct", "ptw_kpi.view") ? [{ href: "/ptw-audits", label: t("ptwAudits"), Icon: GaugeIcon, testId: "nav-ptw-audits" }] : []),
        ...(ac("ptw_appointment.manage", "permit.view") ? [{ href: "/ptw-appointments", label: t("ptwAppointments"), Icon: UserCheck, testId: "nav-ptw-appointments" }] : []),
        ...(ac("ptw_settings.edit", "ptw_zone_profile.edit") ? [{ href: "/ptw-setup", label: t("ptwSetup"), Icon: Cog, testId: "nav-ptw-setup" }] : []),
      ]
    : [];

  const certItems: Item[] = pid
    ? [
        ...(ac("cert_register.view") ? [{ href: "/equipment-deployments", label: t("equipment"), Icon: Forklift, testId: "nav-equipment" }] : []),
        ...(ac("cert_register.view") ? [{ href: "/equipment-certificates", label: t("equipmentCerts"), Icon: FileBadge, testId: "nav-equipment-certs" }] : []),
        ...(ac("cert_register.view") ? [{ href: "/scaffolds", label: t("scaffolds"), Icon: Fence, testId: "nav-scaffolds" }] : []),
        ...(ac("personnel_cert.view") ? [{ href: "/personnel-certificates", label: t("personnelCerts"), Icon: Award, testId: "nav-personnel-certs" }] : []),
        ...(ac("cert_register.view", "defect.raise") ? [{ href: "/defects", label: t("defects"), Icon: Wrench, testId: "nav-defects" }] : []),
        ...(ac("cert_register.view") ? [{ href: "/tpis", label: t("tpis"), Icon: Landmark, testId: "nav-tpis" }] : []),
        ...(ac("cert.check") ? [{ href: "/cert-check", label: t("certCheck"), Icon: ScanSearch, testId: "nav-cert-check" }] : []),
        ...(ac("cert.import") ? [{ href: "/certificate-imports", label: t("certImports"), Icon: Upload, testId: "nav-cert-imports" }] : []),
        ...(ac("cert.blacklist", "personnel_cert.submit", "cert.review") ? [{ href: "/blacklist-register", label: t("blacklist"), Icon: Ban, testId: "nav-blacklist" }] : []),
        ...(ac("cert_kpi.view", "cert_settings.edit") ? [{ href: "/hook-policy", label: t("certSetup"), Icon: Cog, testId: "nav-cert-setup" }] : []),
      ]
    : [];

  // Phase 5 — training (5-training §8).
  const trainingItems: Item[] = pid
    ? [
        ...(ac("training_record.view", "training_session.manage", "training.nominate", "training_attendance.record")
          ? [{ href: "/training-sessions", label: t("trainingSessions"), Icon: Presentation, testId: "nav-training-sessions" }]
          : []),
        ...(ac("training_record.view", "training_record.submit")
          ? [{ href: "/training-records", label: t("trainingRecords"), Icon: BookOpenCheck, testId: "nav-training-records" }]
          : []),
        ...(ac("training_record.view", "training_matrix.edit", "training_kpi.view")
          ? [{ href: "/training-matrix", label: t("trainingMatrix"), Icon: Grid3x3, testId: "nav-training-matrix" }]
          : []),
        ...(ac("training_catalogue.view") ? [{ href: "/training-courses", label: t("trainingCatalogue"), Icon: Library, testId: "nav-training-catalogue" }] : []),
        ...(ac("training.check") && !ac("cert.check") ? [{ href: "/cert-check", label: t("certCheck"), Icon: ScanSearch, testId: "nav-training-check" }] : []),
        ...(ac("training.import") ? [{ href: "/training-imports", label: t("trainingImports"), Icon: Upload, testId: "nav-training-imports" }] : []),
        ...(ac("training_settings.edit", "training_catalogue.view") ? [{ href: "/training-settings", label: t("trainingSettings"), Icon: Cog, testId: "nav-training-settings" }] : []),
      ]
    : [];

  const medicalItems: Item[] = pid
    ? [
        ...(ac("fitness.status_view", "fitness.functional_view", "fitness.clinical_view") ? [{ href: "/worker-health", label: t("workerHealth"), Icon: UserCheck, testId: "nav-worker-health" }] : []),
        ...(ac("fitness.functional_view", "fitness.clinical_view", "fitness.record_clinic", "fitness.submit_external", "fitness.review")
          ? [{ href: "/fitness-assessments", label: t("fitnessAssessments"), Icon: Stethoscope, testId: "nav-fitness-assessments" }]
          : []),
        ...(ac("fitness_referral.raise", "fitness_hold.manage", "fitness.functional_view", "fitness.clinical_view")
          ? [{ href: "/fitness-holds", label: t("fitnessHolds"), Icon: HeartPulse, testId: "nav-fitness-holds" }]
          : []),
        ...(ac("medical_plan.edit", "fitness.functional_view", "fitness.clinical_view") ? [{ href: "/medical-plan", label: t("medicalPlan"), Icon: ClipboardList, testId: "nav-medical-plan" }] : []),
        ...(ac("medical_kpi.view") ? [{ href: "/occupational-health", label: t("occupationalHealth"), Icon: Activity, testId: "nav-occupational-health" }] : []),
        ...(ac("fitness_catalogue.view") ? [{ href: "/fitness-codes", label: t("medicalCatalogue"), Icon: BookMarked, testId: "nav-medical-catalogue" }] : []),
        ...(ac("fitness.import") ? [{ href: "/medical-imports", label: t("medicalImports"), Icon: Upload, testId: "nav-medical-imports" }] : []),
        ...(ac("medical_settings.edit") ? [{ href: "/medical-settings", label: t("medicalSettings"), Icon: Cog, testId: "nav-medical-settings" }] : []),
      ]
    : [];

  const heatItems: Item[] = pid
    ? [
        ...(ac("heat.view") ? [{ href: "/heat-board", label: t("heatBoard"), Icon: Sun, testId: "nav-heat-board" }] : []),
        ...(ac("heat.view") ? [{ href: "/wbgt-readings", label: t("wbgtReadings"), Icon: Thermometer, testId: "nav-wbgt-readings" }] : []),
        ...(ac("heat.view") ? [{ href: "/heat-welfare-checks", label: t("heatWelfare"), Icon: Droplets, testId: "nav-heat-welfare" }] : []),
        ...(ac("heat.view") ? [{ href: "/acclimatisation-plans", label: t("acclimatisation"), Icon: CalendarCheck, testId: "nav-acclimatisation" }] : []),
        ...(ac("heat.view") ? [{ href: "/ban-patrols", label: t("middayBan"), Icon: Ban, testId: "nav-midday-ban" }] : []),
        ...(ac("heat_log.view") ? [{ href: "/heat-illness-log", label: t("heatIllnessLog"), Icon: Siren, testId: "nav-heat-log" }] : []),
        ...(ac("heat_kpi.view") ? [{ href: "/heat-stress", label: t("heatKpis"), Icon: FileBarChart, testId: "nav-heat-kpis" }] : []),
        ...(ac("heat.view") ? [{ href: "/heat-instruments", label: t("heatSetup"), Icon: Cog, testId: "nav-heat-setup" }] : []),
      ]
    : [];

  /* Phase 6d field assurance (191–201; 33 records inspections). */
  const fieldItems: Item[] = pid
    ? [
        ...(ac("field.view") ? [{ href: "/field-overview", label: t("fieldOverview"), Icon: LayoutGrid, testId: "nav-field-overview" }] : []),
        ...(ac("inspection.record") ? [{ href: "/field-inspections/new", label: t("fieldRun"), Icon: ClipboardCheck, testId: "nav-field-run" }] : []),
        ...(ac("field.view") ? [{ href: "/stop-work-orders", label: t("stopWork"), Icon: OctagonAlert, testId: "nav-stop-work" }] : []),
        ...(ac("field.view", "field_audit.conduct") ? [{ href: "/field-audits", label: t("fieldAudits"), Icon: FileSearch, testId: "nav-field-audits" }] : []),
        ...(ac("field.view", "toolbox.record") ? [{ href: "/toolbox-talks", label: t("toolboxTalks"), Icon: MessagesSquare, testId: "nav-toolbox-talks" }] : []),
        ...(ac("field_library.view") ? [{ href: "/checklist-templates", label: t("fieldLibrary"), Icon: ListChecks, testId: "nav-checklist-templates" }] : []),
        ...(ac("field.view") ? [{ href: "/field-kpis", label: t("fieldKpis"), Icon: FileBarChart, testId: "nav-field-kpis" }] : []),
      ]
    : [];

  /* Phase 6e environmental (202–214). */
  const envItems: Item[] = pid && ac("env.view")
    ? [
        { href: "/env-overview", label: t("envOverview"), Icon: Leaf, testId: "nav-env-overview" },
        { href: "/env-aspects", label: t("envAspects"), Icon: ListTree, testId: "nav-env-aspects" },
        { href: "/env-permits", label: t("envPermits"), Icon: FileBadge, testId: "nav-env-permits" },
        { href: "/waste-consignments", label: t("envWaste"), Icon: Truck, testId: "nav-env-waste" },
        { href: "/env-readings", label: t("envMonitoring"), Icon: AudioWaveform, testId: "nav-env-monitoring" },
        { href: "/spills", label: t("envSpills"), Icon: Droplets, testId: "nav-env-spills" },
        { href: "/env-complaints", label: t("envComplaints"), Icon: MessageSquareWarning, testId: "nav-env-complaints" },
        { href: "/env-kpis", label: t("envKpis"), Icon: FileBarChart, testId: "nav-env-kpis" },
      ]
    : [];

  /* Phase 6f incident follow-up (215–223). */
  const followupItems: Item[] = pid
    ? [
        ...(ac("followup.view") ? [{ href: "/followup-overview", label: t("fuOverview"), Icon: LayoutGrid, testId: "nav-fu-overview" }] : []),
        ...(ac("followup.view") ? [{ href: "/notification-register", label: t("fuRegister"), Icon: BellRing, testId: "nav-fu-register" }] : []),
        ...(ac("lesson_library.view") ? [{ href: "/lessons", label: t("fuLessons"), Icon: Lightbulb, testId: "nav-fu-lessons" }] : []),
        ...(ac("followup.view", "lesson.acknowledge") ? [{ href: "/lesson-acknowledgements", label: t("fuAcks"), Icon: MailCheck, testId: "nav-fu-acks" }] : []),
        ...(ac("followup.view") ? [{ href: "/effectiveness-checks", label: t("fuChecks"), Icon: Repeat2, testId: "nav-fu-checks" }] : []),
        ...(ac("followup.view") ? [{ href: "/followup-kpis", label: t("fuKpis"), Icon: FileBarChart, testId: "nav-fu-kpis" }] : []),
        ...(ac("followup.view") ? [{ href: "/followup-settings", label: t("fuSettings"), Icon: SlidersHorizontal, testId: "nav-fu-settings" }] : []),
      ]
    : [];

  /* Phase 6g contractor scorecard (224–228) and reports / exports (229–232). */
  const scorecardItems: Item[] = pid
    ? [
        ...(ac("scorecard.view") ? [{ href: "/scorecards", label: t("scCards"), Icon: Trophy, testId: "nav-sc-cards" }] : []),
        ...(ac("scorecard.comment", "scorecard.resolve") ? [{ href: "/scorecard-remarks", label: t("scRemarks"), Icon: MessageCircleWarning, testId: "nav-sc-remarks" }] : []),
        ...(ac("scorecard.view") ? [{ href: "/watch-list", label: t("scWatch"), Icon: Eye, testId: "nav-sc-watch" }] : []),
        ...(ac("scorecard.view") ? [{ href: "/scorecard-kpis", label: t("scKpis"), Icon: FileBarChart, testId: "nav-sc-kpis" }] : []),
        ...(ac("scorecard.settings") ? [{ href: "/scorecard-settings", label: t("scSettings"), Icon: SlidersHorizontal, testId: "nav-sc-settings" }] : []),
      ]
    : [];
  const reportItems: Item[] = [
    ...(pid && ac("report_pack.view", "report_pack.prepare") ? [{ href: "/report-packs", label: t("rpPacks"), Icon: FileStack, testId: "nav-rp-packs" }] : []),
    ...(ac("export_log.view") ? [{ href: "/exports", label: t("xpExports"), Icon: FileDown, testId: "nav-xp-exports" }] : []),
  ];

  const emergencyItems: Item[] = pid
    ? [
        ...(ac("emergency.view") ? [{ href: "/emergency-board", label: t("emergencyBoard"), Icon: ShieldAlert, testId: "nav-emergency-board" }] : []),
        ...(ac("emergency.view") ? [{ href: "/emergency-events", label: t("emergencyEvents"), Icon: Siren, testId: "nav-emergency-events" }] : []),
        ...(ac("emergency.view") ? [{ href: "/drills", label: t("drills"), Icon: Megaphone, testId: "nav-drills" }] : []),
        ...(ac("emergency.view") ? [{ href: "/emergency-assets", label: t("emergencyAssets"), Icon: FireExtinguisher, testId: "nav-emergency-assets" }] : []),
        ...(ac("emergency.view") ? [{ href: "/emergency-roster", label: t("emergencyRoster"), Icon: Users, testId: "nav-emergency-roster" }] : []),
        ...(ac("emergency.view") ? [{ href: "/emergency-plans", label: t("emergencyPlans"), Icon: LifeBuoy, testId: "nav-emergency-plans" }] : []),
        ...(ac("emergency_kpi.view") ? [{ href: "/emergency-kpis", label: t("emergencyKpis"), Icon: FileBarChart, testId: "nav-emergency-kpis" }] : []),
      ]
    : [];

  return (
    <nav aria-label={t("main")} className="flex flex-1 flex-col gap-5 p-3">
      <ul className="flex flex-col gap-1">
        {main.map((i) => (
          <li key={i.href}>
            <NavLink item={i} onNavigate={onNavigate} />
          </li>
        ))}
      </ul>
      {project ? (
        <div>
          <p className="flex items-center gap-1.5 border-t border-sidebar-border px-3 pt-4 pb-2 text-xs font-medium text-sidebar-muted">
            <span>{t("currentProject")}</span>
            <span aria-hidden>·</span>
            <span className="ltr rounded bg-sidebar-active px-1.5 py-0.5 font-semibold text-sidebar-foreground">{project.code}</span>
          </p>
          {hseItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("hseData")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-hse">
                {hseItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {accessItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("access")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-access">
                {accessItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {ptwItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("ptw")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-ptw">
                {ptwItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {certItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("cert")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-cert">
                {certItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {trainingItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("training")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-training">
                {trainingItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {medicalItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("medical")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-medical">
                {medicalItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {heatItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("heat")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-heat">
                {heatItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {fieldItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("field")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-field">
                {fieldItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {envItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("env")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-env">
                {envItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {followupItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("followup")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-followup">
                {followupItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {scorecardItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("scorecard")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-scorecard">
                {scorecardItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {reportItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("reportsExports")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-reports-exports">
                {reportItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {emergencyItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("emergency")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-emergency">
                {emergencyItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          <ul className="flex flex-col gap-1">
            {projectItems.map((i) => (
              <li key={i.href}>
                <NavLink item={i} onNavigate={onNavigate} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <ul className="mt-auto flex flex-col gap-1 border-t border-sidebar-border pt-3">
        <li>
          <NavLink item={{ href: "/profile", label: t("profile"), Icon: UserRound, testId: "nav-profile" }} onNavigate={onNavigate} />
        </li>
      </ul>
    </nav>
  );
}
