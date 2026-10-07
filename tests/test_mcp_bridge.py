import sys
from pathlib import Path

from rem.config import McpServerConfig
from rem.tools.confirm import ConfirmGate
from rem.tools.mcp_bridge import McpHub

FAKE = str(Path(__file__).parent / "fixtures" / "fake_mcp.py")


async def test_hub_prefixes_tools_and_gates_side_effects():
    gate = ConfirmGate()
    hub = McpHub({"f": McpServerConfig(command=sys.executable, args=[FAKE], prefix="maus", enabled=True)}, confirm=gate)
    await hub.start()
    try:
        assert hub.errors == {}
        assert set(hub.registry.names()) == {"maus__get_note", "maus__send_task"}
        out, err = await hub.registry.call("maus__get_note", {"topic": "x"})
        assert not err and "nota sobre x" in out                      # lectura: sin confirmación
        args = {"bot": "b", "text": "hola"}
        out, _ = await hub.registry.call("maus__send_task", args)
        assert "requiere confirmación" in out                          # efecto: se bloquea
        gate.note_user_message("sí, envíalo")
        out, _ = await hub.registry.call("maus__send_task", args)
        assert "enviado a b: hola" in out                              # tras el "sí" humano, pasa
        out, _ = await hub.registry.call("maus__send_task", args)
        assert "requiere confirmación" in out                          # un solo uso
    finally:
        await hub.close()


async def test_broken_server_does_not_crash_rem():
    hub = McpHub({"x": McpServerConfig(command="no-existe-este-comando", prefix="x", enabled=True)})
    await hub.start()
    assert "x" in hub.errors and hub.registry.names() == []
    await hub.close()


async def test_disabled_servers_are_skipped():
    hub = McpHub({"x": McpServerConfig(command="no-existe", prefix="x", enabled=False)})
    await hub.start()
    assert hub.errors == {} and hub.registry.names() == []
    await hub.close()
