import asyncio
import logging

import pytest

from windows_mcp.infrastructure import run_tool


class TestRunTool:
    async def test_return_value_preserved(self):
        @run_tool()
        async def tool_with_complex_result():
            return {"key": "value", "count": 42}

        assert await tool_with_complex_result() == {"key": "value", "count": 42}

    async def test_error_propagates(self):
        @run_tool()
        async def failing_tool():
            raise ValueError("something broke")

        with pytest.raises(ValueError, match="something broke"):
            await failing_tool()

    async def test_success_is_logged_with_duration(self, caplog):
        @run_tool()
        async def slow_tool():
            await asyncio.sleep(0.1)
            return "done"

        with caplog.at_level(logging.INFO, logger="windows_mcp.infrastructure.dispatch"):
            await slow_tool()

        assert any("slow_tool: SUCCESS" in record.getMessage() for record in caplog.records)

    async def test_error_is_logged(self, caplog):
        @run_tool()
        async def failing_tool():
            raise RuntimeError("fail")

        with caplog.at_level(logging.ERROR, logger="windows_mcp.infrastructure.dispatch"):
            with pytest.raises(RuntimeError):
                await failing_tool()

        assert any("ERROR in failing_tool" in record.getMessage() for record in caplog.records)
