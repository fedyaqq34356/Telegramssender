import os
from dotenv import load_dotenv
import random

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id]

INVITE_CONFIG = {
    "max_invites_per_session": 15,
    "max_invites_per_day": 40,
    "delay_between_invites": (90, 180),
    "delay_after_error": (20, 40),
    "delay_after_privacy": (15, 30)
}

BROADCAST_CONFIG = {
    "max_broadcasts_per_session": 20,
    "max_broadcasts_per_day": 80,
    "delay_between_messages": (90, 180),
    "delay_after_error": (20, 40)
}

def get_random_delay(delay_range):
    if isinstance(delay_range, tuple):
        return random.uniform(delay_range[0], delay_range[1])
    return delay_range