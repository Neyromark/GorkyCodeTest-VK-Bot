from src.bot import bot
from src.handlers import all_handlers

for handler in all_handlers:
    bot.labeler.load(handler)

bot.run()
