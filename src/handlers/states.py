import zoneinfo
from vkbottle import BaseStateGroup, CtxStorage

class UserState(BaseStateGroup):
    WAITING_FOR_AGREEMENT = "waiting_for_agreement"
    REGISTRATION_FIRST_NAME = "registration_first_name"
    REGISTRATION_LAST_NAME = "registration_last_name"
    REGISTRATION_TIMEZONE = "registration_timezone"
    ACCEPT_AGREEMENT = "accept_agreement"

ctx = CtxStorage()
ALL_TIMEZONES = zoneinfo.available_timezones()