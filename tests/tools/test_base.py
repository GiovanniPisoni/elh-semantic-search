"""Offline tests for the tools registry, decorator and dispatcher.

These tests don't touch the database, the LLM, or any external service.
They verify the *contract* of the registry: registration, validation,
dispatch, and error normalisation.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from pydantic import BaseModel, Field

from elh_rag.tools import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
    base,
    execute_tool,
    get_tool,
    list_tools,
    register_tool,
)

# Fixtures


@pytest.fixture(autouse=True)
def _clear_registry():
    """Reset the global registry around each test for isolation."""
    base._clear_registry_for_tests()
    yield
    base._clear_registry_for_tests()


# Sample input models for tests


class _SimpleInput(BaseModel):
    """Minimal input model used by registration tests."""

    name: str
    count: int = Field(ge=0)


class _OtherInput(BaseModel):
    """A second model to exercise multi-tool scenarios."""

    flag: bool = True


# Tests: register_tool decorator


class TestRegisterTool:
    def test_registers_function_with_metadata(self):
        @register_tool(
            name="echo",
            description="Returns the input unchanged.",
            input_model=_SimpleInput,
        )
        def echo(payload: _SimpleInput):
            return payload

        spec = get_tool("echo")
        assert spec.name == "echo"
        assert spec.description == "Returns the input unchanged."
        assert spec.input_model is _SimpleInput
        # Function callable directly with a validated model
        result = spec.func(_SimpleInput(name="foo", count=1))
        assert result.name == "foo"

    def test_decorated_function_is_returned_unchanged(self):
        """The decorator must not wrap the function — direct calls
        must still work for unit tests of tool internals."""

        @register_tool(
            name="passthrough",
            description="...",
            input_model=_SimpleInput,
        )
        def passthrough(payload: _SimpleInput):
            return payload.count * 2

        # Direct call with a model instance
        assert passthrough(_SimpleInput(name="x", count=3)) == 6

    def test_duplicate_name_raises(self):
        @register_tool(
            name="dup",
            description="first",
            input_model=_SimpleInput,
        )
        def first(payload):
            return None

        with pytest.raises(ValueError, match="already registered"):

            @register_tool(
                name="dup",
                description="second",
                input_model=_SimpleInput,
            )
            def second(payload):
                return None

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="non-empty"):

            @register_tool(name="", description="...", input_model=_SimpleInput)
            def f(payload):
                return None

    def test_whitespace_name_raises(self):
        with pytest.raises(ValueError, match="non-empty"):

            @register_tool(name="   ", description="...", input_model=_SimpleInput)
            def f(payload):
                return None

    def test_non_pydantic_input_model_raises(self):
        class NotAModel:
            pass

        with pytest.raises(ValueError, match="BaseModel"):

            @register_tool(
                name="bad",
                description="...",
                input_model=NotAModel,  # type: ignore[arg-type]
            )
            def f(payload):
                return None

    def test_multiple_tools_coexist(self):
        @register_tool(name="a", description="...", input_model=_SimpleInput)
        def a(payload):
            return "a"

        @register_tool(name="b", description="...", input_model=_OtherInput)
        def b(payload):
            return "b"

        assert list_tools() == ["a", "b"]


# Tests: execute_tool dispatcher


class TestExecuteTool:
    def test_runs_with_valid_payload(self):
        @register_tool(
            name="adder",
            description="Add 10 to count.",
            input_model=_SimpleInput,
        )
        def adder(payload: _SimpleInput):
            return {"result": payload.count + 10}

        out = execute_tool("adder", {"name": "x", "count": 5})
        assert out == {"result": 15}

    def test_unknown_tool_raises_not_found(self):
        with pytest.raises(ToolNotFoundError) as exc_info:
            execute_tool("ghost", {})
        assert "ghost" in str(exc_info.value)
        # available list is exposed
        assert exc_info.value.available == []

    def test_unknown_tool_lists_available(self):
        @register_tool(name="real", description="...", input_model=_SimpleInput)
        def real(payload):
            return None

        with pytest.raises(ToolNotFoundError) as exc_info:
            execute_tool("ghost", {"name": "x", "count": 0})
        assert "real" in str(exc_info.value)

    def test_invalid_payload_raises_validation_error(self):
        @register_tool(
            name="strict",
            description="...",
            input_model=_SimpleInput,
        )
        def strict(payload):
            return None

        # Missing required field 'name'
        with pytest.raises(ToolValidationError) as exc_info:
            execute_tool("strict", {"count": 5})
        assert exc_info.value.tool_name == "strict"
        # Original ValidationError is attached
        from pydantic import ValidationError

        assert isinstance(exc_info.value.original, ValidationError)

    def test_payload_violates_pydantic_constraint(self):
        @register_tool(
            name="constrained",
            description="...",
            input_model=_SimpleInput,
        )
        def constrained(payload):
            return None

        # count must be >= 0
        with pytest.raises(ToolValidationError):
            execute_tool("constrained", {"name": "x", "count": -1})

    def test_extra_fields_default_pydantic_behavior(self):
        """Default pydantic v2 behaviour: extra fields silently ignored.

        We document the expectation here; if a tool needs to forbid
        extras, it can set ``model_config = ConfigDict(extra='forbid')``
        on its input model.
        """

        @register_tool(
            name="loose",
            description="...",
            input_model=_SimpleInput,
        )
        def loose(payload: _SimpleInput):
            return payload.count

        out = execute_tool("loose", {"name": "x", "count": 1, "junk": "ignored"})
        assert out == 1

    def test_runtime_error_wrapped_in_execution_error(self):
        @register_tool(
            name="crashy",
            description="...",
            input_model=_SimpleInput,
        )
        def crashy(payload):
            raise RuntimeError("DB connection lost")

        with pytest.raises(ToolExecutionError) as exc_info:
            execute_tool("crashy", {"name": "x", "count": 1})
        assert exc_info.value.tool_name == "crashy"
        assert "DB connection lost" in str(exc_info.value)
        # Original exception preserved for logging
        assert isinstance(exc_info.value.cause, RuntimeError)

    def test_keyboard_interrupt_not_swallowed(self):
        """Critical: tool errors must wrap, but interrupts must propagate."""

        @register_tool(
            name="interruptible",
            description="...",
            input_model=_SimpleInput,
        )
        def interruptible(payload):
            raise KeyboardInterrupt

        # KeyboardInterrupt inherits from BaseException, not Exception,
        # so our `except Exception` will not catch it. Verify.
        with pytest.raises(KeyboardInterrupt):
            execute_tool("interruptible", {"name": "x", "count": 0})

    def test_tool_returning_none_is_ok(self):
        @register_tool(
            name="silent",
            description="...",
            input_model=_SimpleInput,
        )
        def silent(payload):
            return None

        assert execute_tool("silent", {"name": "x", "count": 0}) is None


# Tests: introspection helpers


class TestIntrospection:
    def test_list_tools_empty(self):
        assert list_tools() == []

    def test_list_tools_sorted(self):
        @register_tool(name="zeta", description="...", input_model=_SimpleInput)
        def zeta(p):
            return None

        @register_tool(name="alpha", description="...", input_model=_SimpleInput)
        def alpha(p):
            return None

        @register_tool(name="mu", description="...", input_model=_SimpleInput)
        def mu(p):
            return None

        assert list_tools() == ["alpha", "mu", "zeta"]

    def test_get_tool_returns_spec(self):
        @register_tool(
            name="x",
            description="hello",
            input_model=_SimpleInput,
        )
        def x(p):
            return None

        spec = get_tool("x")
        assert spec.name == "x"
        assert spec.description == "hello"

    def test_get_tool_missing_raises(self):
        with pytest.raises(ToolNotFoundError):
            get_tool("missing")

    def test_tool_spec_is_frozen(self):
        @register_tool(name="frozen", description="...", input_model=_SimpleInput)
        def frozen(p):
            return None

        spec = get_tool("frozen")
        with pytest.raises(FrozenInstanceError):
            # frozen dataclass: assignment should raise FrozenInstanceError
            spec.name = "tampered"  # type: ignore[misc]


# Tests: error class semantics


class TestErrorClasses:
    def test_all_inherit_from_tool_error(self):
        from elh_rag.tools import ToolError

        assert issubclass(ToolNotFoundError, ToolError)
        assert issubclass(ToolValidationError, ToolError)
        assert issubclass(ToolExecutionError, ToolError)

    def test_not_found_carries_available_list(self):
        err = ToolNotFoundError("ghost", available=["a", "b"])
        assert err.name == "ghost"
        assert err.available == ["a", "b"]

    def test_execution_error_preserves_cause(self):
        original = ValueError("upstream")
        err = ToolExecutionError("toolx", message="something broke", cause=original)
        assert err.cause is original
        assert "ValueError" in str(err)
