# MCP PostgreSQL Client 🚀

Welcome to the MCP PostgreSQL Client with Claude 3.5 Sonnet integration!

## Usage

Run the client with:

```bash
chainlit run app/chainlit_app.py -- <path-to-mcp-server> <database-url>

#Example:


chainlit run app/chainlit_app.py
```

You can now interact with your PostgreSQL database using natural language queries. The client will:
1. Process your query using Claude
2. Execute SQL queries when needed
3. Show you the results in a formatted way