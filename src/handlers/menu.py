from vkbottle.bot import BotLabeler, Message

labeler = BotLabeler()
labeler.vbml_ignore_case = True


@labeler.private_message(text=["начать"])
async def handler(message: Message):
    await message.answer("Привет")
