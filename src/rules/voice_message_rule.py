from typing import Union

from vkbottle.bot import Message
from vkbottle.dispatch.rules import ABCRule


class VoiceMessageRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        return True
