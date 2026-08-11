# English Agent

Este projeto nasce como um agente de inglês, mas foi pensado para evoluir em direção a um assistente pessoal.

## Arquitetura proposta

```text
english-agent/
├── app/
│   ├── ai/
│   ├── chat/
│   ├── memory/
│   ├── speech/
│   ├── prompts/
│   ├── startup/
│   └── utils/
├── data/
├── tests/
├── .env
├── main.py
├── requirements.txt
└── README.md
```

## Fases de evolução

### Fase 1 — Conversa
- Chat com IA
- Histórico
- Correção de inglês
- Memória da conversa

### Learning Modes

O agente separa regras globais e regras de modo:

- `app/prompts/system_prompt.py` mantém apenas regras gerais do assistente.
- `app/learning/modes.py` registra os modos `DAILY`, `TEACHER`, `CONVERSATION` e `VOCABULARY`, cada um com suas próprias instruções.
- `ConversationService` combina `System Prompt`, instruções do modo ativo, `PersonalContext` e janela recente da conversa antes de chamar a OpenAI.
- O modo ativo fica em `PersonalContext` como `learning_mode`, com `DAILY` como padrão.

Para alternar no terminal:

```bash
/mode teacher
/mode conversation
/mode vocabulary
/mode daily
```

### Fase 2 — Voz
- IA fala
- Resposta por microfone
- Conversa contínua

### Fase 3 — Assistente
- Bom dia Airton
- Google Calendar
- GitHub
- Jira
- Tempo
- Notícias

### Fase 4 — Jarvis
- Inicialização com o Debian
- Execução em background
- Hotword
- Notificações
- Integração com Ledger

## Execução inicial

```bash
python main.py
```

## Testes

```bash
pytest -q
```
