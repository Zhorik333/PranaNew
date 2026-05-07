"""Repository classes for PranaNew data access."""

from bot.repositories.bookings import BookingsRepository
from bot.repositories.reviews import ReviewsRepository
from bot.repositories.settings import SettingsRepository
from bot.repositories.slots import SlotsRepository
from bot.repositories.users import UsersRepository

__all__ = [
    "BookingsRepository",
    "ReviewsRepository",
    "SettingsRepository",
    "SlotsRepository",
    "UsersRepository",
]
