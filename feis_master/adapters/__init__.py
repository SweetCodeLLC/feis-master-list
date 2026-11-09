from .feisworx import FeisworxAdapter
from .idtana import IdtanaAdapter
from .platforms import FeisWebAdapter, IFeisAdapter
from .quickfeis import QuickFeisAdapter
from .regional import EasternCanadaAdapter, NewEnglandAdapter, SouthernAdapter, WesternCanadaAdapter
from .rss import RssAdapter

REGISTRY = {
    "idtana": IdtanaAdapter,
    "feisworx": FeisworxAdapter,
    "rss": RssAdapter,
    "quickfeis": QuickFeisAdapter,
    "ifeis": IFeisAdapter,
    "feisweb": FeisWebAdapter,
    "western_canada": WesternCanadaAdapter,
    "new_england": NewEnglandAdapter,
    "eastern_canada": EasternCanadaAdapter,
    "southern": SouthernAdapter,
}
