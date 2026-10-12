# Option 7a / 7b design pass (UI/UX): presentation-only strings for the vehicle accident section, the
# accident-report archive card and the incident register (vehDesign.*), and the site-vehicles prototype
# screens (svDesign.*). New keys only; no earlier string is changed.
P = {
    "vehDesign": {
        "vehicleCol": ["Vehicle / report no.", "المركبة / رقم المحضر"],
        "licenceValidUntil": ["valid until {date}", "سارية حتى {date}"],
        "roadDialogHint": [
            "Road, journey and conditions of this accident. Once the investigation is approved, a change needs a reason.",
            "الطريق والرحلة والظروف في هذا الحادث. بعد اعتماد التحقيق يلزم ذكر سبب لأي تعديل.",
        ],
        "vehicleDialogHint": [
            "One vehicle or item of mobile plant involved in this incident. A plate found in the vehicle register fills the vehicle and its documents.",
            "مركبة أو معدة متحركة واحدة لها علاقة بهذا الحادث. اللوحة المسجلة في سجل المركبات تملأ بيانات المركبة ومستنداتها.",
        ],
        "report": {
            "closeCheck": ["Needed to close:", "متطلبات الإغلاق:"],
            "replaceBand": [
                "Replace an archived report file: the current file is kept, marked superseded. This cannot be undone.",
                "استبدال ملف محضر مؤرشف: يبقى الملف الحالي ويُعلَّم بأنه مستبدل. لا يمكن التراجع عن ذلك.",
            ],
            "replaceNamed": ["Upload corrected file for {name}", "رفع ملف مصحح بدلاً من {name}"],
        },
    },
    "svDesign": {
        "todaysCheck": ["today's check", "فحص اليوم"],
        "checkMissingLong": ["Today's pre-use check has not been recorded", "لم يُسجَّل الفحص اليومي لهذا اليوم"],
        "summary": {
            "readinessNow": ["Readiness now", "الجاهزية الآن"],
            "todayAhead": ["Today and the next 30 days", "اليوم والأيام الثلاثون القادمة"],
        },
        "missing": {
            "showAll": ["Show all {n}", "عرض الكل ({n})"],
            "showFewer": ["Show fewer", "عرض أقل"],
        },
        "form": {
            "answered": ["{done} of {total} items answered", "أُجيب عن {done} من {total}"],
            "defects": ["defects: {n}", "العيوب: {n}"],
        },
    },
}
