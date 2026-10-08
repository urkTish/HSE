# Phase 5: training settings, HSE settings register date, hook policy training kind.
P = {
  "hseSettings": {
    "fields": {"training_register_from": ["Training register from", "احتساب التدريب من السجل اعتباراً من"]},
    "trainingRegisterHint": ["K-37 uses training-register hours from this date and daily-return hours before it. Once set it may only move earlier, and never after today.", "يستخدم المؤشر K-37 ساعات سجل التدريب من هذا التاريخ وساعات التقارير اليومية قبله. بعد تعيينه لا يجوز نقله إلا إلى تاريخ أبكر، ولا بعد اليوم."],
  },
  "hookPolicy": {
    "trainingNotEnabled": ["Training hooks are not enabled on this project yet. Read the training readiness report below, then enable them in training settings.", "لم يُفعَّل ربط التدريب في هذا المشروع بعد. اقرأ تقرير جاهزية التدريب أدناه ثم فعّله من إعدادات التدريب."],
    "openTrainingSettings": ["Open training settings", "فتح إعدادات التدريب"],
  },
  "training": {
    "settings": {
      "title": ["Training settings", "إعدادات التدريب"],
      "subtitle": ["Phase 5 rules for this project. Only the allowed ranges are accepted; every change is audited.", "قواعد المرحلة 5 لهذا المشروع. تُقبل النطاقات المسموح بها فقط، وكل تغيير مسجَّل في سجل التدقيق."],
      "readOnly": ["Only the HSE Manager can change these settings.", "مدير الصحة والسلامة فقط يمكنه تغيير هذه الإعدادات."],
      "saved": ["Training settings saved", "تم حفظ إعدادات التدريب"],
      "allowed": ["Allowed: {range}", "المسموح: {range}"],
      "groupRegister": ["Register and hooks", "السجل والربط"],
      "registerFrom": ["Training register from", "احتساب التدريب من السجل اعتباراً من"],
      "notSet": ["Not set (daily returns only)", "غير محدد (التقارير اليومية فقط)"],
      "editInHse": ["Edit in HSE settings", "تعديل في إعدادات الصحة والسلامة"],
      "registerHint": ["K-37 uses register hours from this date. Training hooks can be enabled only when it is set and not after today.", "يستخدم المؤشر K-37 ساعات السجل من هذا التاريخ. لا يمكن تفعيل ربط التدريب إلا إذا كان محدداً وليس بعد اليوم."],
      "hooks": ["Training hooks", "ربط التدريب"],
      "hooksOn": ["Enabled", "مفعّل"], "hooksOff": ["Not enabled", "غير مفعّل"],
      "openHookPolicy": ["Open hook policy", "فتح سياسة الربط"],
      "enableHooks": ["Enable training hooks", "تفعيل ربط التدريب"],
      "enableTitle": ["Enable training hooks?", "تفعيل ربط التدريب؟"],
      "enableHint": ["Training requirements then start their transition: critical courses block first, the others later. This cannot be undone. Read the readiness report first.", "تبدأ متطلبات التدريب عندها مرحلتها الانتقالية: تُحجب الدورات الحرجة أولاً ثم البقية لاحقاً. لا يمكن التراجع عن ذلك. اقرأ تقرير الجاهزية أولاً."],
      "readReadiness": ["Open the training readiness report", "فتح تقرير جاهزية التدريب"],
      "registeredOn": ["Registered on", "تاريخ التسجيل"],
      "registeredOnHint": ["Leave empty for today.", "اتركه فارغاً لاستخدام تاريخ اليوم."],
      "hooksEnabled": ["Training hooks enabled", "تم تفعيل ربط التدريب"],
      "groupRecords": ["Records and verification", "السجلات والتحقق"],
      "groupSessions": ["Sessions and trainers", "الجلسات والمدربون"],
      "groupPlanning": ["Planning and matrix", "التخطيط والمصفوفة"],
      "groupHooks": ["Hook transition", "المرحلة الانتقالية للربط"],
      "f": {
        "training_pass_mark_pct": ["Pass mark (%)", "درجة النجاح (%)"],
        "training_max_attempts_30d": ["Max attempts in 30 days", "الحد الأقصى للمحاولات خلال 30 يوماً"],
        "unverified_training_acceptance_hours": ["Accept unverified records for (hours)", "قبول السجلات غير المتحقق منها لمدة (ساعات)"],
        "training_verification_due_days": ["Verification due (days)", "مهلة التحقق (أيام)"],
        "training_scan_retention_years": ["Scan retention (years)", "مدة الاحتفاظ بالصور الممسوحة (سنوات)"],
        "session_close_deadline_days": ["Close sessions within (days)", "إغلاق الجلسات خلال (أيام)"],
        "session_backdate_max_days": ["Max backdating (days)", "أقصى تأريخ رجعي (أيام)"],
        "session_day_max_net_hours": ["Max net hours per day", "أقصى ساعات صافية في اليوم"],
        "trainer_authorisation_max_months": ["Max trainer authorisation (months)", "أقصى مدة لتفويض المدرب (أشهر)"],
        "refresher_planning_days": ["Refresher planning window (days)", "نافذة تخطيط التنشيط (أيام)"],
        "refresher_max_lapse_days": ["Max refresher lapse (days)", "أقصى انقطاع للتنشيط (أيام)"],
        "matrix_line_max_due_days": ["Max due days on a matrix line", "أقصى أيام استحقاق لبند المصفوفة"],
        "training_matrix_warning_pct": ["Matrix compliance warning below (%)", "تحذير امتثال المصفوفة دون (%)"],
        "training_hook_transition_days": ["Transition days", "أيام المرحلة الانتقالية"],
        "training_hook_critical_transition_days": ["Critical transition days", "أيام المرحلة الانتقالية للدورات الحرجة"],
      },
      "languageBlock": ["Categories blocked on language mismatch", "الفئات المحجوبة عند عدم تطابق اللغة"],
      "addOnly": ["Categories can be added, not removed.", "يمكن إضافة الفئات دون حذفها."],
      "criticalCodes": ["Critical training codes", "رموز التدريب الحرجة"],
      "criticalHint": ["Critical codes block first. Codes can be added, not removed; one added after the critical block date blocks at once.", "تُحجب الرموز الحرجة أولاً. يمكن إضافة الرموز دون حذفها؛ والرمز المضاف بعد تاريخ الحجب الحرج يُحجب فوراً."],
      "validity": ["Course validity on this project", "صلاحية الدورات في هذا المشروع"],
      "validityHint": ["Shorten only. A value on a no-expiry course sets a cap.", "التقصير فقط. القيمة على دورة بلا انتهاء تضع حداً أقصى."],
      "course": ["Course", "الدورة"],
      "catalogueMonths": ["Catalogue (months)", "الكتالوج (أشهر)"],
      "projectMonths": ["Project (months)", "المشروع (أشهر)"],
      "noExpiry": ["No expiry", "بلا انتهاء"],
      "alertSchedule": ["Expiry alerts at {days} days before.", "تنبيهات الانتهاء قبل {days} يوماً."],
      "lastUpdated": ["Last updated {at} by", "آخر تحديث {at} بواسطة"],
    }
  }
}

P["certCheck"] = {
  "training": ["Training", "التدريب"],
  "noTraining": ["No training requirements apply.", "لا تنطبق متطلبات تدريب."],
  "trainee": ["Trainee", "المتدرب"],
  "worker": ["Worker", "عامل"],
  "recordNo": ["Record no.", "رقم السجل"],
  "completedOn": ["Completed", "تاريخ الإكمال"],
  "noExpiry": ["No expiry", "بلا انتهاء"],
  "subtitle": ["Scan an equipment or scaffold sticker, a worker's access card, or the QR on a training certificate. Nothing is recorded except the view.", "امسح ملصق معدة أو سقالة، أو بطاقة دخول عامل، أو رمز QR على شهادة تدريب. لا يُسجَّل شيء سوى الاطلاع."],
}

P["accessSettings"] = {
  "supersededByHookPolicy": ["Training hooks are enabled: this policy is set by the hook policy.", "ربط التدريب مفعّل: تُحدَّد هذه السياسة من سياسة الربط."],
}
