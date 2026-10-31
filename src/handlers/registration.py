import logging
from vkbottle import Keyboard, KeyboardButtonColor, Callback, GroupEventType
from vkbottle.bot import BotLabeler, Message, MessageEvent
from vkbottle.dispatch.rules.base import MessageLengthRule

from src.bot import bot
from src.handlers.states import UserState, ctx, ALL_TIMEZONES
from src.funcs.sender import send_registration
logger = logging.getLogger(__name__)
labeler = BotLabeler()
labeler.vbml_ignore_case = True

@labeler.private_message(text=["начать"])
async def start_handler(message: Message):
    #-------------------------------------------------------------
    #Здесь должна быть проверка на существование пользователя в БД
    #-------------------------------------------------------------
    await message.answer(
        "Привет! 👋\n"
        "Я - бот-помощник по задачам и встречам.\n"
        "Что я умею:\n"
        "• Создавать задачи и встречи из обычного сообщения;\n"
        "• Напоминать о них в нужное время;\n"
        "• Показывать список задач и встреч;\n"
        "• Искать по старым задачам и встречам;\n"
        "• Отвечать на вопросы о ваших записях."
    )

    keyboard = (
        Keyboard(inline=True)
        .add(Callback("👍Принимаю", payload={"cmd": "accept"}), color=KeyboardButtonColor.POSITIVE)
        .add(Callback("👎Не принимаю", payload={"cmd": "decline"}), color=KeyboardButtonColor.NEGATIVE)
    )

    await message.answer(
        "Для использования бота необходимо принять все соглашения и политику конфиденциальности.\n"
        "Ознакомиться с политикой можно тут: https://example.com/privacy\n\n"
        "Вы согласны?",
        keyboard=keyboard.get_json()
    )

    await bot.state_dispenser.set(message.peer_id, UserState.WAITING_FOR_AGREEMENT)

@labeler.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent)
async def handle_agreement_click(event: MessageEvent):
    payload = event.payload
    cmd = payload.get("cmd")
    
    await event.ctx_api.messages.send_message_event_answer(
        event_id=event.event_id,
        user_id=event.user_id,
        peer_id=event.peer_id,
    )

    try:
        await event.ctx_api.messages.delete(
            cmids=[event.conversation_message_id],
            peer_id=event.peer_id,
            delete_for_all=True
        )
    except Exception as e:
        logger.warning(f"⚠️Не удалось удалить сообщение с кнопкой: {e}")

    if cmd == "accept":
        await bot.state_dispenser.set(event.peer_id, UserState.REGISTRATION_FIRST_NAME)
        await event.ctx_api.messages.send(
            peer_id=event.peer_id,
            #--------------------------------------------------------------------
            message="✅Отлично! Давайте теперь познакомимся! Введите ваше имя:",
            #--------------------------------------------------------------------
            random_id=0
        )
    elif cmd == "decline":
        keyboard = (
            Keyboard(inline=True)
            .add(Callback("👍Принимаю", payload={"cmd": "accept"}), color=KeyboardButtonColor.POSITIVE)
        )
        await event.ctx_api.messages.send(
            peer_id=event.peer_id,
            message="😔Сожалеем, но вы не сможете пользоваться нашим ботом без принятия соглашений.\n"
                    "Это важно, так как без этого, бот не сможет работать."
                    "Если передумаете, нажмите кнопку ниже.👇",
            keyboard=keyboard.get_json(),
            random_id=0
        )

# --- Шаги регистрации ---

@labeler.private_message(state=UserState.REGISTRATION_FIRST_NAME)
async def ask_first_name(message: Message):
    first_name = message.text.strip()
    if not first_name:
        await message.answer("⚠️Имя не распознано. Пожалуйста, введите свое имя:")
        return
    
    ctx.set(f"first_name_{message.peer_id}", first_name)
    await bot.state_dispenser.set(message.peer_id, UserState.REGISTRATION_LAST_NAME)
    await message.answer("Теперь введите вашу фамилию:")

@labeler.private_message(state=UserState.REGISTRATION_LAST_NAME)
async def ask_last_name(message: Message):
    last_name = message.text.strip()
    if not last_name:
        await message.answer("⚠️Фамилия не распознана. Пожалуйста, введите свою фамилию:")
        return
    
    ctx.set(f"last_name_{message.peer_id}", last_name)
    await bot.state_dispenser.set(message.peer_id, UserState.REGISTRATION_TIMEZONE)
    await message.answer(
        "И последний шаг. Введите ваш часовой пояс в формате IANA.\n"
        "Например: 'Europe/Moscow или 'Asia/Novosibirsk'.\n\n"
        "Если не знаете часовой пояс своего города, это нормально!\n"
        "Просто загуглите: 'Ваш город' часовой пояс в формате IANA:"
    )

@labeler.private_message(state=UserState.REGISTRATION_TIMEZONE)
async def ask_timezone(message: Message):
    tz = message.text.strip()
    
    if tz not in ALL_TIMEZONES:
        await message.answer(
            "⚠️Не удалось распознать часовой пояс. Проверьте написание.\n"
            "Примеры: `Europe/Moscow`, `Asia/Yekaterinburg`, `Europe/Kaliningrad`.\n"
            "Если не знаете часовой пояс своего города, это нормально!\n\n"
            "Просто загуглите: 'Ваш город' часовой пояс в формате IANA:"
        )
        return

    first_name = ctx.get(f"first_name_{message.peer_id}")
    last_name = ctx.get(f"last_name_{message.peer_id}") # last_name пока не используется

    result = await send_registration(
        session=message.ctx_api.http_client,
        user_id=message.from_id,
        user_name=first_name,
        timezone=tz
    )
    if result is None:
        await message.answer(
            "⚠️ Произошла ошибка при сохранении данных на сервере.\n"
            "Пожалуйста, попробуйте ввести часовой пояс еще раз.\n"
            "Если это не помогло, напишите слово 'Начать'"
        )
        # return
    
    ctx.delete(f"first_name_{message.peer_id}")
    ctx.delete(f"last_name_{message.peer_id}")
    
    await bot.state_dispenser.set(message.peer_id, UserState.ACCEPT_AGREEMENT)
    await message.answer(
        "Регистрация завершена!🎉\n"
        "Теперь вы можете ставить задачи и создавать встречи!\n"
        "Просто напишите или отправьте голосовое сообщение:"
    )