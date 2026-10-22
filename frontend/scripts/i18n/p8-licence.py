# Trial readiness, package B (D-289…D-298): licence banner, licence page, trial terms. New keys only.
# For LICENCE_READ_ONLY / LICENCE_LIMIT_REACHED / LICENCE_KEY_INVALID the server text (message / message_ar,
# with the date, the limit and the counts) is shown first (src/lib/i18n-helpers.ts); these are the fallbacks.
P = {
  "errors": {
    "code": {
      "LICENCE_READ_ONLY": [
        "The licence has ended or is not valid. The platform is read-only: you can view and export, but not add or change records.",
        "انتهى الترخيص أو أنه غير صالح. المنصة الآن للقراءة فقط: يمكنك العرض والتصدير دون إضافة السجلات أو تعديلها.",
      ],
      "LICENCE_LIMIT_REACHED": [
        "A limit of your licence is reached (projects, users, storage or AI questions). Ask for a larger licence.",
        "تم بلوغ أحد حدود ترخيصك (المشاريع أو المستخدمين أو المساحة التخزينية أو أسئلة المساعد الذكي). اطلب ترخيصًا أكبر.",
      ],
      "LICENCE_KEY_INVALID": [
        "This licence key is not valid. Check that it was copied in full.",
        "مفتاح الترخيص هذا غير صالح. تأكد من نسخه كاملًا.",
      ],
    },
  },
  "nav": {
    "licence": ["Licence", "الترخيص"],
  },
  "audit": {
    "entity": {
      "licence": ["Licence", "الترخيص"],
    },
  },
  "licenceBanner": {
    "trial": [
      "{n, plural, =0 {Trial: last day} one {Trial: 1 day left} other {Trial: # days left}}",
      "{n, plural, =0 {الفترة التجريبية: اليوم الأخير} one {الفترة التجريبية: يوم واحد متبقٍ} two {الفترة التجريبية: يومان متبقيان} few {الفترة التجريبية: # أيام متبقية} many {الفترة التجريبية: # يومًا متبقيًا} other {الفترة التجريبية: # يوم متبقٍ}}",
    ],
    "ending": [
      "{n, plural, =0 {The licence ends today} one {The licence ends in 1 day} other {The licence ends in # days}}",
      "{n, plural, =0 {ينتهي الترخيص اليوم} one {ينتهي الترخيص خلال يوم واحد} two {ينتهي الترخيص خلال يومين} few {ينتهي الترخيص خلال # أيام} many {ينتهي الترخيص خلال # يومًا} other {ينتهي الترخيص خلال # يوم}}",
    ],
    "until": ["Last day: {date}.", "آخر يوم: {date}."],
    "expired": ["Licence expired, read-only", "انتهى الترخيص، للقراءة فقط"],
    "invalid": ["Licence key not valid, read-only", "مفتاح الترخيص غير صالح، للقراءة فقط"],
    "readOnlyText": [
      "You can view and export, but not add or change records.",
      "يمكنك العرض والتصدير، دون إضافة السجلات أو تعديلها.",
    ],
    "askManager": [
      "Ask your HSE Manager to enter a new licence key.",
      "اطلب من مدير الصحة والسلامة والبيئة إدخال مفتاح ترخيص جديد.",
    ],
    "deletion": [
      "Trial data will be deleted after {date} unless a plan is chosen.",
      "ستُحذف بيانات الفترة التجريبية بعد {date} ما لم يتم اختيار باقة.",
    ],
    "storage": [
      "Storage {percent}% used ({used} of {limit} GB).",
      "تم استخدام {percent}% من المساحة التخزينية ({used} من {limit} غيغابايت).",
    ],
    "manage": ["Open licence page", "فتح صفحة الترخيص"],
  },
  "licence": {
    "title": ["Licence", "الترخيص"],
    "subtitle": [
      "The licence of this install: plan, last day and usage. To renew, enter a new key below; no restart is needed.",
      "ترخيص هذا النظام: الباقة وآخر يوم والاستخدام. للتجديد أدخل مفتاحًا جديدًا أدناه، دون الحاجة لإعادة التشغيل.",
    ],
    "status": ["Status", "الحالة"],
    "state": {
      "none": ["No licence key", "لا يوجد مفتاح ترخيص"],
      "active": ["Active", "ساري"],
      "expired": ["Expired, read-only", "منتهٍ، للقراءة فقط"],
      "invalid": ["Not valid, read-only", "غير صالح، للقراءة فقط"],
    },
    "bundle": {
      "trial": ["Free trial", "تجربة مجانية"],
      "basic": ["Basic", "الأساسية"],
      "professional": ["Professional", "الاحترافية"],
      "enterprise": ["Enterprise", "المؤسسات"],
    },
    "noKey": [
      "No licence key is installed, so nothing is limited (development or unlicensed install).",
      "لا يوجد مفتاح ترخيص مثبت، لذلك لا توجد أي حدود (بيئة تطوير أو نظام غير مرخّص).",
    ],
    "fields": {
      "customer": ["Customer", "العميل"],
      "bundle": ["Plan", "الباقة"],
      "licenceId": ["Licence number", "رقم الترخيص"],
      "issuedOn": ["Issued on", "تاريخ الإصدار"],
      "validUntil": ["Last day", "آخر يوم"],
      "daysLeft": ["Days left", "الأيام المتبقية"],
      "source": ["Key entered", "مصدر المفتاح"],
      "installedAt": ["Entered at", "وقت الإدخال"],
      "problem": ["Problem", "المشكلة"],
    },
    "source": {
      "database": ["On this page", "من هذه الصفحة"],
      "environment": ["In the server configuration", "في إعدادات الخادم"],
    },
    "usage": {
      "title": ["Usage", "الاستخدام"],
      "projects": ["Open projects", "المشاريع المفتوحة"],
      "users": ["Users", "المستخدمون"],
      "ai": ["AI questions this month", "أسئلة المساعد الذكي هذا الشهر"],
      "storage": ["Storage", "المساحة التخزينية"],
      "of": ["{used} of {limit}", "{used} من {limit}"],
      "unlimited": ["{used} (no limit)", "{used} (بلا حد)"],
      "gbOf": ["{used} GB of {limit} GB", "{used} من {limit} غيغابايت"],
      "gbUnlimited": ["{used} GB (no limit)", "{used} غيغابايت (بلا حد)"],
      "storageDetail": ["Files {files} GB · database {db} GB", "الملفات {files} غيغابايت · قاعدة البيانات {db} غيغابايت"],
      "storageWarning": [
        "Storage is {percent}% full. Remove old files or ask for more storage.",
        "المساحة التخزينية ممتلئة بنسبة {percent}%. احذف ملفات قديمة أو اطلب مساحة إضافية.",
      ],
    },
    "renew": {
      "title": ["Enter a new licence key", "إدخال مفتاح ترخيص جديد"],
      "hint": [
        "Paste the key you received; it starts with HSE1. Spaces and line breaks do not matter.",
        "الصق المفتاح الذي استلمته، ويبدأ بـ HSE1. لا تؤثر المسافات وفواصل الأسطر.",
      ],
      "label": ["Licence key", "مفتاح الترخيص"],
      "submit": ["Save key", "حفظ المفتاح"],
      "saved": ["Licence key saved.", "تم حفظ مفتاح الترخيص."],
      "managerOnly": [
        "Only the HSE Manager can enter a licence key.",
        "يمكن لمدير الصحة والسلامة والبيئة فقط إدخال مفتاح الترخيص.",
      ],
    },
    "trialTerms": {
      "title": ["Trial terms", "شروط الفترة التجريبية"],
      "t1": [
        "The trial is free for 30 days and includes the Basic features plus the AI assistant.",
        "الفترة التجريبية مجانية لمدة 30 يومًا، وتشمل مزايا الباقة الأساسية مع المساعد الذكي.",
      ],
      "t2": [
        "Trial limits: 1 project, 50 users, 10 GB storage and 100 AI questions.",
        "حدود الفترة التجريبية: مشروع واحد، و50 مستخدمًا، و10 غيغابايت تخزين، و100 سؤال للمساعد الذكي.",
      ],
      "t3": [
        "When the trial ends, the platform becomes read-only (view and export only) until a plan is chosen.",
        "عند انتهاء الفترة التجريبية تصبح المنصة للقراءة فقط (العرض والتصدير فقط) حتى يتم اختيار باقة.",
      ],
      "t4": [
        "If a plan is chosen, all data is kept. If not, the data is deleted 30 days after the trial ends (Personal Data Protection Law).",
        "عند اختيار باقة تُحفظ جميع البيانات، وإلا تُحذف البيانات بعد 30 يومًا من انتهاء الفترة التجريبية (نظام حماية البيانات الشخصية).",
      ],
      "deletion": [
        "Deletion date if no plan is chosen: after {date}.",
        "موعد الحذف إذا لم يتم اختيار باقة: بعد {date}.",
      ],
    },
  },
}
