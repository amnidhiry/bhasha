from functools import lru_cache

from app.packs.base import LanguagePack


@lru_cache
def get_pack(code: str) -> LanguagePack:
    if code == "zh":
        from app.packs.zh import ZhPack

        return ZhPack()
    raise KeyError(f"no language pack installed for {code!r}")


INSTALLED = {"zh": "Mandarin Chinese"}
