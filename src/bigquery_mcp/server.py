from bigquery_mcp.app import mcp

import bigquery_mcp.tools.bigquery


def main():
    """Entry point for running the server."""
    mcp.run()


if __name__ == "__main__":
    main()
