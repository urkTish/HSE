"""Emails (outbox) and in-app notifications (spec §7). Recipient language: rule 47."""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.config import get_settings
from app.core.enums import EntityType, Language, NotificationKind, Role, UserStatus
from app.models import EmailMessage, Notification, RoleAssignment, User

TEMPLATES: dict[str, dict[Language, tuple[str, str]]] = {
    "invite": {
        Language.en: (
            "You are invited to the HSE platform",
            "Hello {name},\n\nYou have been invited to the HSE platform. Set your password "
            "within 72 hours:\n{link}\n",
        ),
        Language.ar: (
            "دعوة للانضمام إلى منصة الصحة والسلامة والبيئة",
            "مرحباً {name}،\n\nتمت دعوتك إلى منصة الصحة والسلامة والبيئة. يرجى تعيين كلمة "
            "المرور خلال 72 ساعة:\n{link}\n",
        ),
    },
    "invite_reminder": {
        Language.en: (
            "Reminder: your HSE platform invitation",
            "Your invite expires soon:\n{link}\n",
        ),
        Language.ar: ("تذكير: دعوتك إلى المنصة", "تنتهي صلاحية دعوتك قريباً:\n{link}\n"),
    },
    "password_reset": {
        Language.en: (
            "Reset your HSE platform password",
            "Use this link within 60 minutes to set a new password:\n{link}\n",
        ),
        Language.ar: (
            "إعادة تعيين كلمة المرور",
            "استخدم هذا الرابط خلال 60 دقيقة لتعيين كلمة مرور جديدة:\n{link}\n",
        ),
    },
    "account_locked": {
        Language.en: (
            "Your account was locked",
            "Too many failed logins. Your account is locked for 15 minutes.",
        ),
        Language.ar: ("تم قفل حسابك", "محاولات دخول فاشلة كثيرة. تم قفل حسابك لمدة 15 دقيقة."),
    },
    "new_login": {
        Language.en: ("New login to your account", "A login from a new device or IP: {ip}."),
        Language.ar: ("تسجيل دخول جديد", "تم تسجيل الدخول من جهاز أو عنوان جديد: {ip}."),
    },
    "generic": {
        Language.en: ("{subject_en}", "{body_en}"),
        Language.ar: ("{subject_ar}", "{body_ar}"),
    },
}


def link(path: str, lang: Language) -> str:
    return f"{get_settings().frontend_base_url}/{lang.value}{path}"


def send_email(db: Session, user: User, template: str, **params: str) -> EmailMessage:
    lang = user.preferred_language
    subject, body = TEMPLATES[template][lang]
    values = {"name": user.full_name_ar or user.full_name_en, **params}
    if lang == Language.en:
        values["name"] = user.full_name_en
    msg = EmailMessage(
        to_email=user.email,
        to_user_id=user.id,
        language=lang,
        template=template,
        subject=subject.format(**values),
        body=body.format(**values),
    )
    db.add(msg)
    return msg


def notify(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    kind: NotificationKind,
    title_en: str,
    title_ar: str,
    body_en: str | None = None,
    body_ar: str | None = None,
    entity_type: EntityType | None = None,
    entity_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> None:
    for uid in set(user_ids):
        db.add(
            Notification(
                user_id=uid,
                kind=kind,
                title_en=title_en,
                title_ar=title_ar,
                body_en=body_en,
                body_ar=body_ar,
                entity_type=entity_type,
                entity_id=entity_id,
                project_id=project_id,
            )
        )


def users_with_role(
    db: Session, role: Role, project_ids: Iterable[uuid.UUID] | None = None
) -> list[uuid.UUID]:
    """Active users holding ``role`` today (optionally on given projects)."""
    day = today()
    stmt = select(RoleAssignment).join(User, User.id == RoleAssignment.user_id)
    stmt = stmt.where(RoleAssignment.role == role, User.status == UserStatus.active)
    if project_ids is not None:
        stmt = stmt.where(RoleAssignment.project_id.in_(list(project_ids)))
    return list({a.user_id for a in db.scalars(stmt).all() if a.is_active_on(day)})


def managers(db: Session) -> list[uuid.UUID]:
    return users_with_role(db, Role.hse_manager)
