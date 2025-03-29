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
from app.bot.routers.misc.keyboard import back_keyboard

from .keyboard import user_editor_keyboard, user_info_keyboard

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
    elif target_user.is_blocked:
        subscription_status = _("user_editor:status:blocked_subscription")

    user_status = _("user_editor:status:user_active")
    if target_user.is_blocked:
        user_status = _("user_editor:status:user_blocked")

    # Информация о рефералах
    referral_info = ""
    if target_user.referral:
        referral_info = _("user_editor:referral:invited_by").format(
            referrer_id=target_user.referral.referrer_tg_id,
            date=target_user.referral.created_at.strftime("%Y-%m-%d %H:%M:%S")
        )
    
    # Статистика по рефералам
    referrals_count = len(target_user.referrals_sent)
    active_referrals = sum(1 for ref in target_user.referrals_sent if ref.referred and ref.referred.server_id is not None)
    total_rewards = sum(reward.amount for reward in target_user.referral_rewards) if hasattr(target_user, 'referral_rewards') else 0
    
    if referrals_count > 0:
        referral_info += "\n" + _("user_editor:referral:statistics").format(
            total_count=referrals_count,
            active_count=active_referrals,
            total_rewards=total_rewards
        )

    # История промокодов
    promocodes_info = ""
    if target_user.activated_promocodes:
        promocodes = []
        for p in target_user.activated_promocodes:
            promocode_info = _("user_editor:promocodes:entry").format(
                code=p.code,
                duration=p.duration,
                activation_date=p.activated_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(p, 'activated_at') else 'N/A'
            )
            promocodes.append(promocode_info)
        promocodes_info = _("user_editor:promocodes:history").format(
            codes="\n".join(promocodes)
        )

    # История платежей
    payments_info = ""
    if target_user.transactions:
        payments = []
        for t in target_user.transactions:
            payment_info = _("user_editor:payments:entry").format(
                id=t.payment_id,
                amount=t.amount,
                currency=t.currency,
                status=t.status,
                date=t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                duration=t.duration,
                devices=t.devices
            )
            payments.append(payment_info)
        payments_info = _("user_editor:payments:history").format(
            payments="\n".join(payments)
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
        promocodes_info=promocodes_info,
        payments_info=payments_info,
        user_status=user_status
    )

    await message.bot.edit_message_text(
        text=text,
        chat_id=message.chat.id,
        message_id=main_message_id,
        reply_markup=user_info_keyboard(target_user.tg_id, target_user.is_blocked),
    )


@router.callback_query(F.data.startswith(NavAdminTools.BLOCK_USER), IsAdmin())
async def callback_block_user(
    callback: CallbackQuery, 
    session: AsyncSession, 
    state: FSMContext,
    services: ServicesContainer
) -> None:
    user_id = int(callback.data.split("_")[1])
    target_user = await User.get(session=session, tg_id=user_id)
    
    if not target_user:
        await callback.answer(_("user_editor:error:user_not_found"))
        return
    
    # Сохраняем предыдущий сервер для возможной разблокировки
    previous_server_id = target_user.server_id
    
    # Если у пользователя есть сервер, удаляем его VPN
    if target_user.server:
        try:
            await services.vpn_manager.delete_client(
                server=target_user.server,
                vpn_id=target_user.vpn_id
            )
        except Exception as e:
            logger.error(f"Failed to delete VPN for user {user_id}: {e}")
            await callback.answer(_("user_editor:message:block_failed"))
            return
    
    # Блокируем пользователя и отключаем его подписку
    success = await User.update_block_status(session=session, tg_id=user_id, blocked=True, server_id=None)
    
    if success:
        # Отправляем уведомление пользователю
        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=_("user_editor:notification:user_blocked")
            )
        except Exception as e:
            logger.error(f"Failed to send block notification to user {user_id}: {e}")

        await callback.answer(_("user_editor:message:user_blocked").format(user_id=user_id))
        target_user = await User.get(session=session, tg_id=user_id)
        if target_user:
            await process_user_id(callback.message, state, session)
    else:
        await callback.answer(_("user_editor:message:block_failed"))


@router.callback_query(F.data.startswith(NavAdminTools.UNBLOCK_USER), IsAdmin())
async def callback_unblock_user(
    callback: CallbackQuery, 
    session: AsyncSession, 
    state: FSMContext
) -> None:
    user_id = int(callback.data.split("_")[1])
    success = await User.update_block_status(session=session, tg_id=user_id, blocked=False)
    
    if success:
        # Отправляем уведомление пользователю
        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=_("user_editor:notification:user_unblocked")
            )
        except Exception as e:
            logger.error(f"Failed to send unblock notification to user {user_id}: {e}")

        await callback.answer(_("user_editor:message:user_unblocked").format(user_id=user_id))
        target_user = await User.get(session=session, tg_id=user_id)
        if target_user:
            await process_user_id(callback.message, state, session)
    else:
        await callback.answer(_("user_editor:message:block_failed"))
