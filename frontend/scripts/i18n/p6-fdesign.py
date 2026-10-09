# Phase 6d design pass (UI/UX): presentation-only strings for the field assurance screens (checklist run,
# toolbox attendance, audit grading, KPI breakdown labels). New keys, plus the talk "may not have understood"
# note, which read "1 attendee(s)" (now an ICU plural).
P = {
    "fdDesign": {
        "answeredOf": ["{done} of {total} answered", "تمت الإجابة على {done} من {total}"],
        "failingN": [
            "{n, plural, one {# not compliant} other {# not compliant}}",
            "{n, plural, zero {لا عدم مطابقة} one {بند واحد غير مطابق} two {بندان غير مطابقين} few {# بنود غير مطابقة} many {# بندًا غير مطابق} other {# بند غير مطابق}}",
        ],
        "nextItem": ["Next item to do", "البند التالي"],
        "toAnswer": [
            "{n, plural, one {# item to answer} other {# items to answer}}",
            "{n, plural, one {بند واحد بحاجة إلى إجابة} two {بندان بحاجة إلى إجابة} few {# بنود بحاجة إلى إجابة} many {# بندًا بحاجة إلى إجابة} other {# بند بحاجة إلى إجابة}}",
        ],
        "toComplete": [
            "{n, plural, one {# not-compliant item needs a note or photo} other {# not-compliant items need a note or photo}}",
            "{n, plural, one {بند غير مطابق يحتاج إلى ملاحظة أو صورة} two {بندان غير مطابقين يحتاجان إلى ملاحظة أو صورة} few {# بنود غير مطابقة تحتاج إلى ملاحظة أو صورة} many {# بندًا غير مطابق يحتاج إلى ملاحظة أو صورة} other {# بند غير مطابق يحتاج إلى ملاحظة أو صورة}}",
        ],
        "manualMissing": ["Describe each added finding", "صِف كل ملاحظة مضافة"],
        "stopMissing": ["Fill in the stop-work details", "أكمل بيانات إيقاف العمل"],
        "readyToSend": ["Every item answered. Ready to submit.", "تمت الإجابة على كل البنود. جاهز للإرسال."],
        "saveOnPhone": ["Save on this phone", "حفظ على هذا الهاتف"],
        "offlineSubmit": [
            "No signal: it is kept on this phone and sent when the signal returns.",
            "لا توجد تغطية: يُحفظ على هذا الهاتف ويُرسل عند عودة الإشارة.",
        ],
        "consequence": ["Finding: {grade}", "ملاحظة: {grade}"],
        "gradeScale": ["Grade scale", "سلم التقدير"],
        "gradeCapped": [
            "Capped at C: a major nonconformity on a critical item.",
            "حُدّد بالتقدير C: عدم مطابقة رئيسية في بند حرج.",
        ],
        "findingsBy": ["Findings by grade", "الملاحظات حسب التقدير"],
        "weakest": ["Lowest section", "أدنى قسم"],
        "dangerZone": ["Record actions", "إجراءات السجل"],
        "suggestedWhy": ["Why suggested", "سبب الاقتراح"],
        "talkLanguage": ["Understands the talk language", "يفهم لغة الاجتماع"],
    },
    "field": {
        "talks": {
            "mismatchNote": [
                "{n, plural, one {# attendee may not have understood: consider an interpreter.} other {# attendees may not have understood: consider an interpreter.}}",
                "{n, plural, one {قد لا يكون حاضر واحد قد فهم: فكّر في الاستعانة بمترجم.} two {قد لا يكون حاضران قد فهما: فكّر في الاستعانة بمترجم.} few {قد لا يكون # حاضرين قد فهموا: فكّر في الاستعانة بمترجم.} many {قد لا يكون # حاضرًا قد فهموا: فكّر في الاستعانة بمترجم.} other {قد لا يكون # حاضر قد فهموا: فكّر في الاستعانة بمترجم.}}",
            ],
        },
    },
    "enums": {
        # Phase 1 inspection types (reference list `inspection_type`): the KPI breakdown rows carry the raw code.
        "fdInspectionType": {
            "general_site": ["General site", "تفتيش عام للموقع"],
            "scaffold": ["Scaffold", "السقالات"],
            "lifting_equipment": ["Lifting equipment", "معدات الرفع"],
            "electrical": ["Electrical", "الكهرباء"],
            "excavation": ["Excavation", "الحفريات"],
            "housekeeping": ["Housekeeping", "نظافة الموقع"],
            "fire_safety": ["Fire safety", "السلامة من الحريق"],
            "welfare": ["Welfare", "المرافق والرعاية"],
            "airside_fod_walk": ["Airside FOD walk", "جولة الأجسام الغريبة في الجانب الجوي"],
            "plant_vehicle": ["Plant & vehicles", "المعدات والمركبات"],
            "environmental": ["Environmental", "البيئة"],
            "ppe": ["PPE", "معدات الوقاية الشخصية"],
            "leadership_walk": ["Leadership walk", "جولة القيادة"],
        },
    },
}
