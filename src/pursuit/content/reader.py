"""Typed, strict access to JSON objects for the content loader."""

from __future__ import annotations

from typing import Any


class ContentError(Exception):
    """A content file is malformed or refers to something that does not exist."""


_MISSING: Any = object()


class Reader:
    """Reads fields from one JSON object and reports errors with their JSON path.

    Call `done()` after reading every field. It rejects keys that nothing read, so a
    typo in a data file fails at load time instead of being silently ignored.
    """

    def __init__(self, data: Any, path: str) -> None:
        if not isinstance(data, dict):
            raise ContentError(f"{path}: expected an object, got {type(data).__name__}")
        self.data: dict[str, Any] = data
        self.path = path
        self._used: set[str] = set()

    def at(self, key: str) -> str:
        return f"{self.path}.{key}"

    def has(self, key: str) -> bool:
        return key in self.data

    def _get(self, key: str, kinds: tuple[type, ...], name: str, default: Any) -> Any:
        self._used.add(key)
        if key not in self.data:
            if default is _MISSING:
                raise ContentError(f"{self.path}: missing required field '{key}'")
            return default
        value = self.data[key]
        if isinstance(value, bool) and bool not in kinds:
            raise ContentError(f"{self.at(key)}: expected {name}, got a boolean")
        if not isinstance(value, kinds):
            raise ContentError(f"{self.at(key)}: expected {name}, got {type(value).__name__}")
        return value

    def get_str(self, key: str, default: Any = _MISSING) -> Any:
        return self._get(key, (str,), "a string", default)

    def get_int(self, key: str, default: Any = _MISSING) -> Any:
        return self._get(key, (int,), "an integer", default)

    def get_bool(self, key: str, default: Any = _MISSING) -> Any:
        return self._get(key, (bool,), "true or false", default)

    def get_list(self, key: str, default: Any = _MISSING) -> Any:
        return self._get(key, (list,), "a list", default)

    def get_dict(self, key: str, default: Any = _MISSING) -> Any:
        return self._get(key, (dict,), "an object", default)

    def get_obj(self, key: str) -> Reader:
        return Reader(self.get_dict(key), self.at(key))

    def opt_obj(self, key: str) -> Reader | None:
        value = self.get_dict(key, None)
        return None if value is None else Reader(value, self.at(key))

    def get_enum(self, key: str, allowed: tuple[str, ...] | frozenset[str], default: Any = _MISSING) -> Any:
        value = self.get_str(key, default)
        if value is not default and value not in allowed:
            options = ", ".join(sorted(allowed))
            raise ContentError(f"{self.at(key)}: '{value}' is not one of: {options}")
        return value

    def get_str_tuple(self, key: str, allowed: tuple[str, ...] | frozenset[str] | None = None) -> tuple[str, ...]:
        """Read a string or a list of strings. A missing key gives an empty tuple."""
        self._used.add(key)
        if key not in self.data:
            return ()
        value = self.data[key]
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, list) or not all(isinstance(v, str) for v in items):
            raise ContentError(f"{self.at(key)}: expected a string or a list of strings")
        if allowed is not None:
            for item in items:
                if item not in allowed:
                    options = ", ".join(sorted(allowed))
                    raise ContentError(f"{self.at(key)}: '{item}' is not one of: {options}")
        return tuple(items)

    def objects(self, key: str, default: Any = _MISSING) -> list[Reader]:
        items = self.get_list(key, default)
        if items is default and default is not _MISSING:
            return []
        return [Reader(item, f"{self.at(key)}[{i}]") for i, item in enumerate(items)]

    def done(self) -> None:
        unknown = set(self.data) - self._used - {"_comment"}
        if unknown:
            raise ContentError(f"{self.path}: unknown field(s): {', '.join(sorted(unknown))}")
