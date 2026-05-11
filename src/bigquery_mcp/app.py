from fastmcp import FastMCP

mcp = FastMCP(
    name="BigQuery MCP Server",
    instructions=(
        "You are a BigQuery assistant. Use the available tools to help users "
        "discover datasets, inspect table schemas, validate queries with dry-run, "
        "and execute read-only SQL queries against BigQuery."
    ),
)
