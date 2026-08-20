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

### Daily Companion + Scheduler

As conversas iniciadas pelo agente ficam em uma camada separada:

- `app/daily/sessions.py` define `DailySession`, janelas de horário e o estado mínimo de execução diária.
- `app/daily/scheduler.py` decide quais sessões devem rodar no momento atual.
- `DailySchedulerRunner` mantém o scheduler ativo enquanto o agente está aberto no terminal.
- `app/daily/topics.py` escolhe temas locais, sem buscar notícias reais.
- `app/daily/companion_prompt.py` contém a personalidade companion.
- `DailySession` usa o `ConversationService`, então OpenAI, memória, `PersonalContext` e Learning Modes continuam centralizados no fluxo existente.

Sessões iniciais:

- `morning`: 08:30 até 09:00.
- `afternoon`: 14:00 até 14:30.

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
