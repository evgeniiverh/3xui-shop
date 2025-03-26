import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import IsAdmin
from app.bot.models import ServicesContainer
from app.bot.utils.constants import MAIN_MESSAGE_ID_KEY
from app.bot.utils.navigation import NavAdminTools
from app.db.models import User

from .keyboard import user_editor_keyboard, back_keyboard

logger = logging.getLogger(__name__)
router = Router(name=__name__)


class UserSearchStates(StatesGroup):
    waiting_for_user_id = State()


async def show_user_editor(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    main_message_id = data.get(MAIN_MESSAGE_ID_KEY)
    current_state = await state.get_state()

    text = _("user_editor:message:main")
    reply_markup = user_editor_keyboard()

    if current_state == UserSearchStates.waiting_for_user_id:
        text = _("user_editor:message:enter_user_id")
        reply_markup = back_keyboard(NavAdminTools.USER_EDITOR_BACK)

    await message.bot.edit_message_text(
        text=text,
        chat_id=message.chat.id,
        message_id=main_message_id,
        reply_markup=reply_markup,
    )


@router.callback_query(F.data == NavAdminTools.USER_EDITOR, IsAdmin())
async def callback_user_editor(callback: CallbackQuery, user: User, state: FSMContext) -> None:
    logger.info(f"Admin {user.tg_id} opened user editor.")
    await state.set_state(None)
    await show_user_editor(message=callback.message, state=state)


@router.callback_query(F.data == NavAdminTools.USER_EDITOR_BACK, IsAdmin())
async def callback_user_editor_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await show_user_editor(message=callback.message, state=state)


@router.callback_query(F.data == NavAdminTools.SEARCH_USER, IsAdmin())
async def callback_search_user(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserSearchStates.waiting_for_user_id)
    await show_user_editor(message=callback.message, state=state)


@router.message(UserSearchStates.waiting_for_user_id, IsAdmin())
async def process_user_id(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user_id = message.text
    if not user_id.isdigit():
        await message.reply(_("user_editor:error:invalid_user_id"))
        return

    target_user = await User.get(session=session, tg_id=int(user_id))
    if not target_user:
        await message.reply(_("user_editor:error:user_not_found"))
        return

    await state.set_state(None)
    await message.delete()

    data = await state.get_data()
    main_message_id = data.get(MAIN_MESSAGE_ID_KEY)

    subscription_status = _("user_editor:status:no_subscription")
    if target_user.server:
        subscription_status = _("user_editor:status:active_subscription")

    referral_info = ""
    if target_user.referral:
        referral_info = _("user_editor:referral:invited_by").format(
            referrer_id=target_user.referral.referrer_tg_id,
            date=target_user.referral.created_at.strftime("%Y-%m-%d %H:%M:%S")
        )
    
    referrals_count = len(target_user.referrals_sent)
    if referrals_count > 0:
        referral_info += "\n" + _("user_editor:referral:invited_users").format(count=referrals_count)

    promocodes_info = ""
    if target_user.activated_promocodes:
        promocodes = [f"{p.code} ({p.duration} days)" for p in target_user.activated_promocodes]
        promocodes_info = _("user_editor:promocodes:used").format(
            codes=", ".join(promocodes)
        )

    text = _("user_editor:message:user_info").format(
        user_id=target_user.tg_id,
        username=target_user.username or "N/A",
        first_name=target_user.first_name,
        created_at=target_user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        subscription_status=subscription_status,
        server=target_user.server.name if target_user.server else "N/A",
        language=target_user.language_code,
        trial_used=_("global:yes") if target_user.is_trial_used else _("global:no"),
        referral_info=referral_info,
        promocodes_info=promocodes_info
    )

    await message.bot.edit_message_text(
        text=text,
        chat_id=message.chat.id,
        message_id=main_message_id,
        reply_markup=back_keyboard(NavAdminTools.USER_EDITOR_BACK),
    )
