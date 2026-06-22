import json
import re

from enum import Enum
from pathlib import Path


class DictTag(Enum):
    POKEMON = "pokemon"
    ABILITY = "ability"
    ITEM = "item"
    MOVE = "move"
    NATURE = "nature"


class Dict:
    _zh_to_tag_pokemon = None
    _zh_to_tag_ability = None
    _zh_to_tag_item = None
    _zh_to_tag_move = None
    _zh_to_tag_nature = None

    _eng_dict_pokemon = None
    _eng_dict_ability = None
    _eng_dict_item = None
    _eng_dict_move = None
    _eng_dict_nature = None

    def __new__(cls):
        cls._load_dicts()
        return super().__new__(cls)

    @classmethod
    def _lookup_zh_tag(cls, tag: DictTag, text: str) -> str:
        cls._load_dicts()
        if text is None or not str(text).strip():
            raise KeyError(f"{tag.value} text is empty.")

        reverse_dict = getattr(cls, f"_zh_to_tag_{tag.value}")
        normalized_text = cls._normalize_lookup_text(str(text).strip())
        eng_key = reverse_dict.get(normalized_text)
        if not eng_key:
            raise KeyError(f"Chinese text not found in locale mapping: {text}")
        return eng_key

    @classmethod
    def _lookup_english_text_by_tag(cls, tag: DictTag, eng_key: str) -> str:
        cls._load_dicts()
        eng_dict = getattr(cls, f"_eng_dict_{tag.value}")
        eng_value = eng_dict.get(eng_key)
        if not eng_value:
            raise KeyError(f"English locale value not found for key: {eng_key}")
        return eng_value

    @classmethod
    def lookup_zh_english_text(cls, tag: DictTag, text: str) -> str:
        eng_key = cls._lookup_zh_tag(tag, text)
        return cls._lookup_english_text_by_tag(tag, eng_key)

    @classmethod
    def _load_dicts(cls):
        if cls._zh_to_tag_pokemon is not None:
            return

        base_dir = cls._find_locale_base_dir()
        base_dir_zh = base_dir / "zh" / "pokemon"
        base_dir_eng = base_dir / "en" / "pokemon"

        def load_reverse_dict(filename: str, tag: DictTag):
            path = base_dir_zh / filename
            if not path.exists():
                return {}
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            reverse_dict = {}
            for key, value in data.items():
                if key == "@@locale":
                    continue
                for normalized_value in cls._expand_reverse_values(tag, value):
                    reverse_dict[normalized_value] = key
            return reverse_dict

        def load_eng_dict(filename: str):
            path = base_dir_eng / filename
            if not path.exists():
                return {}
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)

        cls._zh_to_tag_pokemon = load_reverse_dict("pokemon.zh.json", DictTag.POKEMON)
        cls._zh_to_tag_ability = load_reverse_dict("ability.zh.json", DictTag.ABILITY)
        cls._zh_to_tag_item = load_reverse_dict("item.zh.json", DictTag.ITEM)
        cls._zh_to_tag_move = load_reverse_dict("move.zh.json", DictTag.MOVE)
        cls._zh_to_tag_nature = load_reverse_dict("nature.zh.json", DictTag.NATURE)

        cls._eng_dict_pokemon = load_eng_dict("pokemon.en.json")
        cls._eng_dict_ability = load_eng_dict("ability.en.json")
        cls._eng_dict_item = load_eng_dict("item.en.json")
        cls._eng_dict_move = load_eng_dict("move.en.json")
        cls._eng_dict_nature = load_eng_dict("nature.en.json")

    @classmethod
    def _expand_reverse_values(cls, tag: DictTag, value: str) -> set[str]:
        normalized_values = {cls._normalize_lookup_text(value)}
        if tag == DictTag.NATURE:
            short_value = re.split(r"\s{2,}", value, maxsplit=1)[0]
            normalized_values.add(cls._normalize_lookup_text(short_value))
        return {item for item in normalized_values if item}

    @staticmethod
    def _find_locale_base_dir() -> Path:
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "resources" / "locales"
            if candidate.exists():
                return candidate
        return Path(__file__).resolve().parent.parent / "resources" / "locales"

    @staticmethod
    def _normalize_lookup_text(text: str | None) -> str:
        if text is None:
            return ""
        return (
            str(text)
            .translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            .replace(" ", "")
            .replace("\u3000", "")
            .strip()
        )
