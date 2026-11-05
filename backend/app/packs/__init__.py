"""Language-pack registry. Packs register a factory; the core asks for them by code."""

from collections.abc import Callable

from app.packs.base import LanguagePack

_FACTORIES: dict[str, tuple[str, Callable[[], LanguagePack]]] = {}
_INSTANCES: dict[str, LanguagePack] = {}


def register(code: str, name: str, factory: Callable[[], LanguagePack]) -> None:
    _FACTORIES[code] = (name, factory)
    _INSTANCES.pop(code, None)


def unregister(code: str) -> None:
    _FACTORIES.pop(code, None)
    _INSTANCES.pop(code, None)


def get_pack(code: str) -> LanguagePack:
    if code not in _INSTANCES:
        if code not in _FACTORIES:
            raise KeyError(f"no language pack installed for {code!r}")
        _INSTANCES[code] = _FACTORIES[code][1]()
    return _INSTANCES[code]


def _clear() -> None:
    _INSTANCES.clear()


get_pack.cache_clear = _clear  # type: ignore[attr-defined]  # tests reset packs between runs


class _Installed(dict):
    """code -> display name, live view of the registry."""

    def __iter__(self):
        return iter(_FACTORIES)

    def __contains__(self, code):
        return code in _FACTORIES

    def items(self):
        return [(c, n) for c, (n, _) in _FACTORIES.items()]

    def keys(self):
        return list(_FACTORIES)

    def __getitem__(self, code):
        return _FACTORIES[code][0]

    def __len__(self):
        return len(_FACTORIES)


INSTALLED = _Installed()


def _zh() -> LanguagePack:
    from app.packs.zh import ZhPack

    return ZhPack()


register("zh", "Mandarin Chinese", _zh)
