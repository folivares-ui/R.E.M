from mcp.server import MCPServer

srv = MCPServer("fake")


@srv.tool()
def get_note(topic: str) -> str:
    """Lee una nota (solo lectura)."""
    return f"nota sobre {topic}"


@srv.tool()
def send_task(bot: str, text: str) -> str:
    """Envía trabajo a un bot (tiene efectos)."""
    return f"enviado a {bot}: {text}"


if __name__ == "__main__":
    srv.run("stdio")
