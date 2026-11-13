"""
The contracts of values read from and written as JSON, and the base that validates data
read from outside as pydantic dataclasses.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Self, get_args

from pydantic import (
    AliasChoices,
    AliasPath,
    ConfigDict,
    GetCoreSchemaHandler,
    TypeAdapter,
)
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pydantic.fields import FieldInfo
from pydantic_core import core_schema

from basstler.class_property import classproperty
from basstler.exceptions import DuplicateKeyError

# %% the reading contract


class JSONModel(ABC):
    """
    A dataclass mirroring one object read from outside the program, able to read itself
    from it.

    Each model reads only its own object's fields and hands each nested object to that
    object's own model.
    """

    @classmethod
    @abstractmethod
    def from_json(cls, data: dict[str, Any]) -> JSONModel:
        """
        Read one of these out of the object it mirrors.

        :param data: The object to read.
        :return: The parsed model.
        """


# %% the writing contract


class JSONSerializable(ABC):
    """
    A value written out as one JSON object.
    """

    @abstractmethod
    def to_json(self) -> dict[str, Any]:
        """:return: The object written for it."""


# %% the validated model


class ValidatedJSONModel(JSONModel, JSONSerializable):
    """
    A frozen pydantic dataclass by subclassing alone, whose fields are the object's
    keys, each spelled as its field name or alias.

    Copied from krrood's ``ValidatedDataclass`` :cite:`krrood` until krrood's light core
    is released.
    """

    __pydantic_config__ = ConfigDict(validate_by_name=True, validate_by_alias=True)
    """
    The pydantic settings every subclass starts from.
    """

    def __init_subclass__(cls, config: ConfigDict | None = None, **kwargs: Any) -> None:
        """
        Make the subclass a frozen pydantic dataclass.

        :param config: Pydantic settings added to those the subclass inherits.
        :param kwargs: Passed on to the next base.
        :raises DuplicateKeyError: If two of its fields read the same key.
        """
        super().__init_subclass__(**kwargs)
        cls.__pydantic_config__ = ConfigDict(
            **cls.__pydantic_config__, **(config or {})
        )
        pydantic_dataclass(cls, frozen=True)
        readers: dict[str, str] = {}
        for name, field_info in cls.__pydantic_fields__.items():
            for key in cls.entry_keys(name, field_info):
                if key in readers:
                    raise DuplicateKeyError(cls.__name__, key, (readers[key], name))
                readers[key] = name

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        """
        :raises pydantic.ValidationError: If the object does not have the model's shape.
        """
        return TypeAdapter(cls).validate_python(data)

    def to_json(self) -> dict[str, Any]:
        """
        :return: The object, each field written under its alias where it has one.
        """
        return TypeAdapter(type(self)).dump_python(self, mode="json", by_alias=True)

    @classproperty
    def read_keys(cls) -> frozenset[str]:
        """
        Every key the model reads out of its object, at any depth.
        """
        keys: set[str] = set()
        for name, field_info in cls.__pydantic_fields__.items():
            keys |= cls.field_keys(name, field_info)
            for model in cls.nested_models(field_info.annotation):
                keys |= model.read_keys
        return frozenset(keys)

    @staticmethod
    def field_keys(name: str, field_info: FieldInfo) -> set[str]:
        """
        :param name: The field's name.
        :param field_info: The field.
        :return: Every key the field is read from, each step of a nested key path
            included.
        """
        return {
            step
            for path in ValidatedJSONModel.key_paths(name, field_info)
            for step in path
            if isinstance(step, str)
        }

    @staticmethod
    def entry_keys(name: str, field_info: FieldInfo) -> set[str]:
        """
        :param name: The field's name.
        :param field_info: The field.
        :return: The keys of the model's own object the field is read from.
        """
        return {path[0] for path in ValidatedJSONModel.key_paths(name, field_info)}

    @staticmethod
    def key_paths(name: str, field_info: FieldInfo) -> list[list[str | int]]:
        """
        :param name: The field's name.
        :param field_info: The field.
        :return: Each path of keys the field can be read from, outermost key first.
        """
        alias = field_info.validation_alias or field_info.alias or name
        choices = alias.choices if isinstance(alias, AliasChoices) else [alias]
        return [
            list(choice.path) if isinstance(choice, AliasPath) else [choice]
            for choice in choices
        ]

    @staticmethod
    def nested_models(annotation: Any) -> list[type[ValidatedJSONModel]]:
        """
        :param annotation: A field's type.
        :return: Every model the type holds, at any depth of its type arguments.
        """
        if isinstance(annotation, type) and issubclass(annotation, ValidatedJSONModel):
            return [annotation]
        return [
            model
            for argument in get_args(annotation)
            for model in ValidatedJSONModel.nested_models(argument)
        ]


# %% reading a raw value


class RawValueReader(ABC):
    """
    A field annotation that turns the value the data holds into the one the field's type
    validates.
    """

    @abstractmethod
    def read(self, value: Any) -> Any:
        """
        :param value: The value as the data holds it.
        :return: The value the field's type validates.
        """

    def __get_pydantic_core_schema__(
        self, source: type[Any], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """
        :param source: The field's type.
        :param handler: Builds pydantic's own schema for a type.
        :return: How pydantic reads the field: :meth:`read`, then the field's type.
        """
        return core_schema.no_info_before_validator_function(self.read, handler(source))
