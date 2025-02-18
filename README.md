# MCP Client

A Python client implementation for the Model Context Protocol (MCP) that integrates with Claude 3.5 Sonnet.

## Prerequisites

- Python 3.12 or higher
- PostgreSQL database
- Node.js (for running the PostgreSQL MCP server)
- `uv` package manager (recommended) or `pip`

## Installation

1. Clone the repository:

2. Create and activate a virtual environment:

```bash 
# Create virtual environment
uv venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On Unix or MacOS:
source .venv/bin/activate



```


3. Install dependencies

```bash
# For python equivalent of:
# Install required packages
uv add mcp anthropic python-dotenv

# or install from requirements.txt

# For node:
npm init

npm install @modelcontextprotocol/server-postgres
```

4. Create a `.env` file in the project root and add your Anthropic API key:

```bash
ANTHROPIC_API_KEY=your_api_key_here
```



## Usage

The client can be run with the following command structure:

```bash
uv run client.py <path-to-mcp-server> <database-url>
```

For example:

```bash
uv run client.py ./node_modules/@modelcontextprotocol/server-postgres/dist/index.js postgresql://localhost/your_database
```


Where:
- `<path-to-mcp-server>` is the path to the MCP server JavaScript file
- `<database-url>` is your PostgreSQL connection string

Once running, you can interact with the client through the command line interface. Type your queries and type 'quit' to exit.

## Features

- Interactive chat interface with Claude 3.5 Sonnet
- Integration with PostgreSQL database through MCP
- Support for both Python and JavaScript MCP servers
- Tool-based query processing

## Development

The project uses:
- `anthropic` for Claude API integration
- `mcp` for Model Context Protocol implementation
- `python-dotenv` for environment variable management

## License

MIT License