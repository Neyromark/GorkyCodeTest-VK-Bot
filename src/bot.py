import os

from vkbottle import API
from vkbottle.bot import Bot, BotLabeler

api = API(token=os.getenv("VK_TOKEN", "TOKEN"))
labeler = BotLabeler()
bot = Bot(labeler=labeler, api=api)
