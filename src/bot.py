import os

from vkbottle import API
from vkbottle.bot import Bot, BotLabeler

token = os.getenv("VK_TOKEN")
if not token:
    raise RuntimeError("Переменная окружения VK_TOKEN не задана (проверьте .env)")

api = API(token=token)

labeler = BotLabeler()
labeler.vbml_ignore_case = True

bot = Bot(labeler=labeler, api=api)
