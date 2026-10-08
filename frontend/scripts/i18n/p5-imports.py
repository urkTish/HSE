# Phase 5: training imports.
P = {
  "training": {
    "imports": {
      "title": ["Training imports", "استيراد التدريب"],
      "subtitle": ["Upload training records or session attendance. The file is checked first; nothing is saved until you commit.", "ارفع سجلات التدريب أو حضور الجلسات. يُفحص الملف أولاً، ولا يُحفظ شيء حتى تعتمد الاستيراد."],
      "check": ["Check file", "فحص الملف"], "checking": ["Checking…", "جارٍ الفحص…"],
      "template": ["Template", "القالب"], "source": ["Source", "المصدر"],
      "registerHint": ["The provider's own register, sent by email. Records get a confirmed verification and are still reviewed.", "سجل الجهة نفسها مرسلاً بالبريد. تحصل السجلات على تحقق مؤكد وتبقى خاضعة للمراجعة."],
      "session": ["Session", "الجلسة"], "sessionHint": ["Delivered sessions only. Closing stays a separate step.", "الجلسات المنفذة فقط. يبقى الإغلاق خطوة منفصلة."],
      "file": ["File", "الملف"], "fileHint": [".csv or .xlsx, up to 5 MB and 5,000 rows. English or Arabic headers.", "‎.csv أو ‎.xlsx، حتى 5 ميغابايت و5,000 صف. عناوين إنجليزية أو عربية."],
      "scansZip": ["Certificate scans (.zip)", "صور الشهادات (‎.zip)"], "scansHint": ["Optional. Files named <certificate_no>.pdf, .jpg or .png. Rows without a scan stay Draft.", "اختياري. ملفات باسم <رقم_الشهادة>.pdf أو ‎.jpg أو ‎.png. تبقى الصفوف دون صورة مسودة."],
      "provider": ["Provider", "الجهة"],
      "evidence": ["Provider's email (PDF / EML)", "بريد الجهة (PDF / EML)"], "evidenceHint": ["Must come from one of the provider's verification domains.", "يجب أن يكون من أحد نطاقات التحقق الخاصة بالجهة."],
      "templates": ["Templates", "القوالب"], "excelEn": ["Excel (English)", "Excel (إنجليزي)"], "excelAr": ["Excel (Arabic)", "Excel (عربي)"],
      "history": ["Import history", "سجل الاستيراد"], "noImports": ["No imports yet.", "لا توجد عمليات استيراد بعد."],
      "fileName": ["File", "الملف"], "uploadedBy": ["Uploaded by", "رفعه"],
      "counts": {
        "rows_total": ["Rows", "الصفوف"], "rows_ok": ["OK", "سليمة"], "rows_warning": ["Warnings", "تحذيرات"], "rows_error": ["Errors", "أخطاء"],
        "records_created": ["Records created", "السجلات المنشأة"], "records_left_draft": ["Left as Draft", "بقيت مسودة"], "attendance_rows_applied": ["Attendance rows applied", "صفوف الحضور المطبقة"],
      },
      "reportTitle": ["Import check", "فحص الاستيراد"],
      "openSession": ["Open session", "فتح الجلسة"],
      "scansFound": ["Scans: {name} ({n} files)", "الصور: {name} ({n} ملف)"],
      "evidenceFile": ["Evidence: {name}", "المستند: {name}"],
      "sensitive": ["Contains ID numbers: stored encrypted and deleted at commit, discard or expiry.", "يحتوي على أرقام هوية: يُحفظ مشفراً ويُحذف عند الاعتماد أو الإلغاء أو انتهاء المهلة."],
      "fileIssues": ["The file cannot be imported", "لا يمكن استيراد الملف"],
      "partialCommit": ["{ok} rows can be imported; {err} rows with errors will be skipped.", "يمكن استيراد {ok} صف؛ وسيتم تجاوز {err} صف بها أخطاء."],
      "nothingValid": ["No row can be imported.", "لا يوجد صف قابل للاستيراد."],
      "submittedNote": ["Imported records are Submitted for review, never Accepted.", "تُقدَّم السجلات المستوردة للمراجعة ولا تُقبل تلقائياً."],
      "attendanceNote": ["Committed rows update the session's attendance. Close the session separately.", "تحدّث الصفوف المعتمدة حضور الجلسة. أغلق الجلسة بشكل منفصل."],
      "expiresAt": ["Commit before {time}.", "اعتمد قبل {time}."],
      "commit": ["Import {n} rows", "استيراد {n} صف"], "discard": ["Discard", "إلغاء"],
      "committed": ["{n} imported", "تم استيراد {n}"], "discarded": ["Import discarded", "تم إلغاء الاستيراد"],
      "expiredNote": ["This check expired after 60 minutes. Upload the file again.", "انتهت صلاحية هذا الفحص بعد 60 دقيقة. ارفع الملف مجدداً."],
      "committedNote": ["{n} records created ({draft} left as Draft without a scan).", "تم إنشاء {n} سجل ({draft} بقيت مسودة دون صورة)."],
      "committedAttendance": ["{n} attendance rows applied.", "تم تطبيق {n} صف حضور."],
      "viewRecords": ["View submitted records", "عرض السجلات المقدّمة"],
      "rows": ["Rows", "الصفوف"], "showOk": ["Show OK rows", "إظهار الصفوف السليمة"], "noIssues": ["No row issues.", "لا توجد مشكلات في الصفوف."],
      "rowNo": ["Row", "الصف"], "codes": ["Codes", "الرموز"], "messages": ["Messages", "الرسائل"], "worker": ["Worker", "العامل"],
      "dayNo": ["Day", "اليوم"], "certificate": ["Certificate", "الشهادة"], "scan": ["Scan", "الصورة"], "scanYes": ["Found", "موجودة"], "scanNo": ["Missing", "مفقودة"],
    }
  }
}
