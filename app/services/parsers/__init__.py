from .base import registry
from .hh import HHParser
from .habr import HabrParser
from .kwork import KworkParser
from .fl import FLParser
from .superjob import SuperJobParser
from .rabota import RabotaParser
from .zarplata import ZarplataParser
from .telegram import TelegramParser
from .workzilla import WorkZillaParser

__all__ = [
    "registry",
    "HHParser",
    "HabrParser",
    "KworkParser",
    "FLParser",
    "SuperJobParser",
    "RabotaParser",
    "ZarplataParser",
    "TelegramParser",
    "WorkZillaParser",
]
