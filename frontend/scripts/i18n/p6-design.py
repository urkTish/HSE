# Phase 6a design pass (UI/UX): presentation-only strings for the occupational health screens. New keys only,
# plus the Arabic "Revoke" action, which read إلغاء ("Cancel") and sat next to real cancel buttons.
P = {
  "medDesign": {
    "confidential": ["Confidential health data: each view is recorded.", "بيانات صحية سرية: يُسجَّل كل اطلاع عليها."],
    "raisedOn": ["Raised", "تاريخ الإحالة"],
    "noHolds": ["No fitness holds on this project.", "لا توجد إيقافات لأسباب اللياقة في هذا المشروع."],
    "noReferrals": ["No fitness referrals on this project.", "لا توجد إحالات لتقييم اللياقة في هذا المشروع."],
    "noAssessments": ["No fitness assessments on this project yet.", "لا توجد تقييمات لياقة في هذا المشروع بعد."],
    "state": {
      "label": ["Fitness for work", "الأهلية للعمل"],
      "onHold": ["Removed from work", "مُبعَد عن العمل"],
      "onHoldLine": ["Pending HSE check. No site entry and no permit crew until the hold is released.", "لحين مراجعة السلامة. لا دخول إلى الموقع ولا انضمام إلى طاقم تصريح حتى رفع الإيقاف."],
      "stop": ["Not eligible — stops work", "غير مؤهل — يوقف العمل"],
      "stopLine": ["Fitness requirement not met. Work that needs these codes is blocked:", "متطلب اللياقة غير مستوفى. الأعمال التي تتطلب هذه الرموز محظورة:"],
      "check": ["Fitness check needed", "يلزم فحص اللياقة"],
      "checkLine": ["Not cleared on every requirement. Codes to check:", "غير مستوفٍ لكل المتطلبات. الرموز المطلوب فحصها:"],
      "cleared": ["Cleared for work", "مؤهل للعمل"],
      "clearedLine": ["Every fitness requirement on this project is met.", "جميع متطلبات اللياقة في هذا المشروع مستوفاة."],
      "none": ["No fitness requirements", "لا توجد متطلبات لياقة"],
      "noneLine": ["No fitness code applies to this worker on this project.", "لا ينطبق أي رمز لياقة على هذا العامل في هذا المشروع."],
    },
  },
  "enums": {
    "assessmentAction": {
      "revoke": ["Revoke", "إلغاء التقييم"],
    },
  },
}
