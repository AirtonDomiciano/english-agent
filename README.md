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
