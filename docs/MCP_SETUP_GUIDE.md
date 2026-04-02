# Emily MCP Servers Setup Guide

This guide documents the MCP (Model Context Protocol) servers configured for Emily AI system and provides setup instructions.

## Current MCP Configuration

Emily now has **15 MCP servers** configured, providing comprehensive capabilities across multiple domains:

### Core Infrastructure (11 existing)
- **context7**: Live library documentation
- **filesystem**: File read/write operations
- **github**: GitHub integration (requires `GITHUB_TOKEN`)
- **brave-search**: Web search (requires `BRAVE_API_KEY`)
- **memory**: Persistent knowledge graph
- **sequential-thinking**: Complex reasoning
- **sqlite**: Database queries for episodic memory
- **qdrant**: Vector search for semantic memory
- **fetch**: Web page to markdown conversion
- **git**: Git operations
- **time**: Timezone and temporal operations

### Newly Added (4 new)
- **playwright**: Browser automation and testing
- **postgres**: PostgreSQL database access
- **n8n-mcp**: Workflow automation
- **cloudflare-docs**: Cloudflare services integration
- **slack**: Slack workspace integration

## Environment Variables Setup

Create a `.env` file based on `.env.example` and configure the following variables:

### Required for Core Functionality
```bash
# GitHub integration
GITHUB_TOKEN=your_github_personal_access_token_here

# Web search
BRAVE_API_KEY=your_brave_search_api_key_here
```

### Optional Extensions
```bash
# PostgreSQL database
POSTGRES_URL=postgresql://username:password@hostname:port/database

# n8n workflow automation
N8N_API_URL=https://your-n8n-instance.com
N8N_API_KEY=your-n8n-api-key-here

# Cloudflare services
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token_here
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id_here

# Slack integration
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token-here
SLACK_USER_TOKEN=xoxp-your-slack-user-token-here
```

## New MCP Server Capabilities

### 1. Playwright MCP Server
**Purpose**: Browser automation, web testing, UI interactions
**Features**:
- Automated website testing and monitoring
- AI-powered E2E test creation
- Web scraping and data extraction
- Screenshot capture and visual analysis
- Multi-browser support (Chrome, Firefox, Safari)

**Usage Examples**:
- "Take a screenshot of https://example.com"
- "Fill out the contact form on our website"
- "Test the checkout flow and report any issues"

### 2. PostgreSQL MCP Server
**Purpose**: Direct database access and SQL queries
**Features**:
- Natural language to SQL translation
- Schema inspection and analysis
- Data-driven AI dashboards
- Real-time ERP/CRM automation

**Usage Examples**:
- "Show me all users who signed up last week"
- "What's our average order value by region?"
- "Create a dashboard of sales performance"

### 3. n8n MCP Server
**Purpose**: Workflow automation and integration
**Features**:
- Create and manage n8n workflows
- Trigger business processes
- Multi-step automation chains
- Enterprise logic flow orchestration

**Usage Examples**:
- "Create a workflow that sends a Slack message when a new user signs up"
- "Set up automated email sequences for lead nurturing"
- "Build a data pipeline from CRM to analytics"

### 4. Cloudflare MCP Server
**Purpose**: Cloud infrastructure management
**Features**:
- Workers deployment and management
- KV, R2, D1 database operations
- Analytics and monitoring
- Edge deployment and routing

**Usage Examples**:
- "Deploy a new Cloudflare Worker for our API"
- "Check our R2 storage usage and costs"
- "Set up edge caching for our static assets"

### 5. Slack MCP Server
**Purpose**: Team communication and collaboration
**Features**:
- Channel management and messaging
- Thread interactions and replies
- User information and presence
- Message history and search

**Usage Examples**:
- "Post a summary of today's activities to #general"
- "Find all messages about the project deadline"
- "Create a new channel for the marketing team"

## Installation Verification

Test the new MCP servers with these commands:

```bash
# Test Playwright
npx @playwright/mcp@latest --version

# Test PostgreSQL (requires database URL)
npx @modelcontextprotocol/server-postgres --version

# Test n8n integration
npx n8n-mcp --version

# Test Cloudflare (requires API credentials)
npx @cloudflare/mcp-server-cloudflare --version

# Test Slack (requires tokens)
npx @modelcontextprotocol/server-slack --version
```

## Configuration Files

### MCP Configuration
- **Location**: `.cursor/mcp.json`
- **Format**: JSON with server definitions
- **Auto-reload**: Changes picked up by IDE restart

### Environment Variables
- **Template**: `.env.example`
- **Active**: `.env` (create from template)
- **Security**: Never commit `.env` to version control

## Security Considerations

1. **API Keys**: Store in environment variables, never in code
2. **Permissions**: Grant minimum required permissions for each service
3. **Network**: Some MCP servers require internet access
4. **Sandboxing**: File system access is restricted to configured paths

## Troubleshooting

### Common Issues

1. **MCP Server Not Starting**
   - Check Node.js installation: `node --version`
   - Verify package availability: `npx <package-name> --version`
   - Check environment variables: `env | grep MCP`

2. **Authentication Errors**
   - Verify API tokens are correct and active
   - Check token permissions and scopes
   - Ensure environment variables are loaded

3. **Connection Issues**
   - Check network connectivity
   - Verify firewall settings
   - Confirm service URLs are accessible

### Debug Mode

Enable debug logging by setting `LOG_LEVEL=debug` in environment variables for individual MCP servers.

## Next Steps

1. **Configure Required Variables**: Set up GitHub and Brave Search API keys
2. **Optional Integrations**: Configure PostgreSQL, n8n, Cloudflare, or Slack as needed
3. **Test Functionality**: Verify each MCP server works with Emily
4. **Monitor Usage**: Check Emily's agent system integration
5. **Documentation**: Update team documentation with new capabilities

## Support

For issues with specific MCP servers:
- Check the respective GitHub repositories
- Review MCP documentation at https://modelcontextprotocol.io/
- Test with MCP Inspector: `npx @modelcontextprotocol/inspector`

---

**Last Updated**: 2026-02-25
**Emily Version**: 1.0.0
**MCP Servers Count**: 15
