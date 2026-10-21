# Setup Guide

## 1. Criar Slack App (uma vez, pelo admin)

1. Acesse https://api.slack.com/apps → **Create New App** → **From scratch**
2. Nome: ex. `Claude MCP`, selecione o workspace
3. Menu lateral → **OAuth & Permissions**
4. Em **Redirect URLs**, adicione: `http://localhost:9876/callback`
5. Em **User Token Scopes** (NÃO Bot Token Scopes), adicione:
   - `channels:read`, `groups:read` — listar canais
   - `channels:history`, `groups:history` — ler histórico de canais
   - `im:history`, `mpim:history` — ler histórico de DM e DM de grupo
   - `chat:write` — postar mensagens
   - `search:read` — buscar mensagens
   - `reactions:write`, `reactions:read` — reactions
   - `users:read` — info de usuários
   - `files:read` — baixar arquivos compartilhados
6. Clique em **Install to Workspace** → **Allow**
7. Copie o **User OAuth Token** (`xoxp-...`) que aparece

## 2. Configurar no Claude Code

Existem **dois modos**: token direto (simples) ou OAuth (escalável).

---

### Modo A: Token Direto (uso pessoal)

Use o token `xoxp-...` que você copiou no passo 1.

```bash
claude mcp add slack \
  -e SLACK_USER_TOKEN=xoxp-seu-token-aqui \
  -- uv --directory /Users/barte/workspace/barte/slack-mcp-server run slack-mcp-server
```

Ou via `.mcp.json`:

```json
{
  "mcpServers": {
    "slack": {
      "command": "uv",
      "args": ["--directory", "/Users/barte/workspace/barte/slack-mcp-server", "run", "slack-mcp-server"],
      "env": {
        "SLACK_USER_TOKEN": "xoxp-seu-token-aqui"
      }
    }
  }
}
```

Pronto. Sem OAuth, sem browser, sem callback. Só colar e usar.

---

### Modo B: OAuth (uso em equipe)

Cada pessoa faz OAuth com a própria conta. O admin compartilha o Client ID/Secret.

**Admin** (uma vez):
1. Criar o Slack App (passo 1 acima)
2. Ir em **Basic Information** → copiar **Client ID** e **Client Secret**
3. Adicionar redirect URL: `http://localhost:9876/callback`
4. Compartilhar Client ID e Client Secret com o time

**Cada dev**:
```bash
claude mcp add slack \
  -e SLACK_CLIENT_ID=123456789.987654321 \
  -e SLACK_CLIENT_SECRET=abcdef1234567890 \
  -- uv --directory /Users/barte/workspace/barte/slack-mcp-server run slack-mcp-server
```

Depois, no Claude Code, pedir: "autentique no Slack" → abre browser → autoriza → pronto.

---

## 3. Usar

Depois de configurado, peça coisas como:

- "Liste os canais do Slack"
- "Poste 'Bom dia!' no canal #general"
- "Busque mensagens sobre deploy no Slack"
- "Leia as últimas 10 mensagens do canal #engineering"
- "Adicione um :thumbsup: na última mensagem"

## 4. Testar Localmente

```bash
uv sync                              # Instalar dependências
uv run pytest -v                     # Rodar testes
uv run ruff check src/ tests/        # Lint
```

## FAQ

### Precisa rodar um server local?

**Não.** O Claude Code gerencia o processo automaticamente via stdio. Quando você configura no `.mcp.json` ou via `claude mcp add`, o Claude Code inicia e para o processo conforme necessário.

### Onde ficam os tokens?

- **Modo token direto**: na env var, não salva nada em disco
- **Modo OAuth**: em `~/.slack-mcp-server/tokens.db` (SQLite)

### Qual modo usar?

| | Token Direto | OAuth |
|---|---|---|
| Setup | Colar token | Client ID + Secret + browser |
| Multi-user | Cada um cria seu App | 1 App, cada um faz OAuth |
| Token refresh | Manual (se expirar) | Automático |
| Melhor para | Uso pessoal | Equipe |

### Por que User Token (xoxp) e não Bot Token?

- Mensagens aparecem como enviadas por **você**
- `search:read` **só funciona** com user tokens
- Mais natural para uso pessoal via Claude Code
