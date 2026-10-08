# Phase 3 design pass (UI/UX): presentation-only strings for the PTW screens. New keys only.
P = {
  "ptwDesign": {
    "gasPrefix": ["Gas:", "الغاز:"],
    "days": ["{d} d", "{d} ي"],
    "stateLabel": ["Permit state", "حالة التصريح"],
    "pausedNow": ["· Paused", "· متوقف مؤقتاً"],
    "state": {
      "draft": ["Draft — not yet requested. Not valid for work.", "مسودة — لم يُطلب بعد. غير صالح للعمل."],
      "requested": ["Waiting for review. Not valid for work.", "بانتظار المراجعة. غير صالح للعمل."],
      "reviewed": ["Reviewed, waiting for approval. Not valid for work.", "تمت المراجعة، بانتظار الاعتماد. غير صالح للعمل."],
      "approved": ["Approved. Not valid for work until it is issued at the site.", "معتمد. غير صالح للعمل حتى يُصدر في الموقع."],
      "issued": ["Issued. Work starts when the receiver starts the shift with the crew.", "صادر. يبدأ العمل عندما يبدأ المستلم الوردية مع الطاقم."],
      "active": ["Work in progress under this permit.", "العمل جارٍ بموجب هذا التصريح."],
      "paused": ["Work paused. The crew is on a break.", "العمل متوقف مؤقتاً. الطاقم في استراحة."],
      "suspended": ["Work stopped. It may continue only after the permit is resumed or revalidated.", "العمل متوقف. لا يُستأنف إلا بعد استئناف التصريح أو إعادة التحقق منه."],
      "closed": ["Closed. The work is finished and the area handed back.", "مغلق. انتهى العمل وسُلّمت المنطقة."],
      "cancelled": ["Cancelled. Not valid for work.", "ملغى. غير صالح للعمل."],
      "expired": ["Expired. Not valid for work.", "منتهي الصلاحية. غير صالح للعمل."],
    },
    "inWindow": ["In today's work window until", "ضمن نافذة العمل اليوم حتى"],
    "outsideWindow": ["Outside the work window. Next window opens", "خارج نافذة العمل. تبدأ النافذة التالية"],
    "noMoreWindows": ["No further work window within the validity.", "لا توجد نافذة عمل أخرى ضمن مدة الصلاحية."],
    "blockersCount": ["{n, plural, one {# blocker stops the next step} other {# blockers stop the next step}}", "{n, plural, one {معوق واحد يمنع الخطوة التالية} two {معوقان يمنعان الخطوة التالية} few {# معوقات تمنع الخطوة التالية} many {# معوقاً يمنع الخطوة التالية} other {# معوق يمنع الخطوة التالية}}"],
    "noBlockersShort": ["No blockers", "لا توجد معوقات"],
    "stopGroup": ["Stop work", "إيقاف العمل"],
    "endGroup": ["Cannot be undone", "لا يمكن التراجع عنه"],
    "irreversible": ["This cannot be undone. Check the permit number before you confirm.", "لا يمكن التراجع عن هذا الإجراء. تحقق من رقم التصريح قبل التأكيد."],
  },
}
P["ptwDesign"].update({
  "likelihood": ["Likelihood (L)", "الاحتمالية (L)"],
  "severity": ["Severity (S)", "الشدة (S)"],
})
P["ptwDesign"].update({
  "limit": ["Limit", "الحد"],
  "outOfLimit": ["out of limit", "خارج الحد"],
  "gasPassLine": ["Every reading is within the applied limits.", "جميع القراءات ضمن الحدود المطبقة."],
  "gasFailLine": ["A reading is outside the limits. Do not start or continue work.", "قراءة خارج الحدود. لا تبدأ العمل ولا تستمر فيه."],
})
P["ptwDesign"].update({
  "lockOn": ["On", "مركّب"],
  "lockCutWarning": ["Cutting a personal lock cannot be undone. Cut only after the holder has been searched for and confirmed absent from the equipment.", "قطع القفل الشخصي لا يمكن التراجع عنه. لا تقطعه إلا بعد البحث عن صاحبه والتأكد من أنه ليس عند المعدة."],
})

# Permit print: enum labels in both languages ("EN|AR"), built from the existing enum messages so the printed
# permit shows status, work types, crew roles and gas results bilingually (presentation only).
import json as _json
import os as _os

_M = _os.path.join(_os.path.dirname(__file__), "..", "..", "messages")
with open(_os.path.join(_M, "en.json"), encoding="utf-8") as _f:
    _EN = _json.load(_f)["enums"]
with open(_os.path.join(_M, "ar.json"), encoding="utf-8") as _f:
    _AR = _json.load(_f)["enums"]
P["ptwBi"] = {
    _ns: {_k: [f"{_v}|{_AR[_ns][_k]}", f"{_v}|{_AR[_ns][_k]}"] for _k, _v in _EN[_ns].items()}
    for _ns in ("permitStatus", "permitType", "ptwCrewRole", "gasResult", "signaturePurpose")
}

_BI3 = {
  "ptwFrom": "From|من",
  "ptwTo": "To|إلى",
  "ptwAuthorisation": "Authorisation and acceptance|الاعتماد والاستلام",
  "ptwRoleCol": "Role|الدور",
  "ptwNameCol": "Name|الاسم",
  "ptwSignCol": "Signature|التوقيع",
  "ptwDateCol": "Date / time|التاريخ / الوقت",
  "ptwSignNote": "Electronic signatures are recorded in the platform (see the audit hash). Sign here only for the paper copy at the work site.|التوقيعات الإلكترونية مسجلة في المنصة (انظر بصمة التدقيق). وقّع هنا لنسخة الموقع الورقية فقط.",
  "ptwControlled": "Controlled copy — check the live status by scanning the QR code|نسخة مضبوطة — تحقق من الحالة الفعلية بمسح رمز QR",
}
P["accessPrint"] = {k: [v, v] for k, v in _BI3.items()}
P["ptwDesign"].update({
  "keepPermit": ["Keep the permit", "الإبقاء على التصريح"],
  "goBack": ["Go back", "رجوع"],
})
