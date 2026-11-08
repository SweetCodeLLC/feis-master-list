from .feisworx import FeisworxAdapter
from .idtana import IdtanaAdapter
from .platforms import FeisWebAdapter, IFeisAdapter
from .quickfeis import QuickFeisAdapter
from .rss import RssAdapter

REGISTRY = {
    "idtana": IdtanaAdapter,
    "feisworx": FeisworxAdapter,
    "rss": RssAdapter,
    "quickfeis": QuickFeisAdapter,
    "ifeis": IFeisAdapter,
    "feisweb": FeisWebAdapter,
}
