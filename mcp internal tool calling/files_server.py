import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("files-server")
BASE_DIR = "./workspace"
os.makedirs(BASE_DIR, exist_ok=True)

@mcp.tool()
def write_file(filename: str, content: str) -> str:
    """Write content to a file"""
    path = os.path.join(BASE_DIR, filename)
    with open(path, "w") as f:
        f.write(content)
    return f"Wrote to {filename}"

@mcp.tool()
def read_file(filename: str) -> str:
    """Read content from a file"""
    path = os.path.join(BASE_DIR, filename)
    with open(path, "r") as f:
        return f.read()

if __name__ == "__main__":
    mcp.run(transport="stdio")