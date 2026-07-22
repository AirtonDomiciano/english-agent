# Fase 2 - IA Conversacional

## Objetivo

O agente consegue conversar com você usando a OpenAI, lembrar da conversa e agir como seu professor de inglês.

## Sprint 2.1 - Integrar OpenAI

Hoje:

```text
Você
 ↓
ConversationService
 ↓
Texto fixo
```

Vai ficar:

```text
Você
 ↓
ConversationService
 ↓
OpenAI
 ↓
Resposta da IA
```

## Sprint 2.2 - Prompt do agente

Criar o arquivo `app/prompts/system_prompt.py`:

```python
SYSTEM_PROMPT = """
You are Airton's personal English assistant.

Your objectives:

- Teach English naturally.
- Correct grammar politely.
- Ask one question at a time.
- Speak like a friend.
- Remember previous conversations.
- Use simple English.
- If Airton writes in Portuguese,
  answer in English and explain the correction.
"""
```

Esse prompt será o "cérebro" do agente.

## Sprint 2.3 - Memória

Hoje existe apenas o JSON.

Agora precisamos usar ele.

Fluxo:

```text
Carregar histórico

↓

Enviar histórico para OpenAI

↓

Receber resposta

↓

Salvar resposta
```

## Sprint 2.4 - Contexto

O agente começa a conhecer você.

Exemplo:

```json
{
  "name": "Airton",
  "country": "Brazil",
  "profession": "Software Engineer",
  "projects": [
    "Ledger",
    "English Agent",
    "DriveHub"
  ],
  "english_level": "B1"
}
```

Quando conversar:

```text
Good morning Airton!

How is Ledger going?
```

Sem precisar explicar toda vez.

## Sprint 2.5 - Chat real

Rodando:

```bash
python main.py
```

Aparece:

```text
English Agent
>
```

Você:

```text
Hoje acordei cansado.
```

IA:

```text
Nice!

A natural way to say that is:

"I woke up tired today."

Why do you think you feel tired?
```

## Sprint 2.6 - Comandos

Começar a entender comandos:

```text
/help
/history
/clear
/vocabulary
/interview
/grammar
/daily
```

## Resultado da Fase 2

Você já terá um agente que conversa.

```text
+---------------------------+
|        YOU                |
+------------+--------------+
             |
             |
             ▼
+---------------------------+
| Conversation Service      |
+------------+--------------+
             |
             ▼
+---------------------------+
| Conversation Memory       |
+------------+--------------+
             |
             ▼
+---------------------------+
| System Prompt             |
+------------+--------------+
             |
             ▼
+---------------------------+
| OpenAI                    |
+------------+--------------+
             |
             ▼
+---------------------------+
| AI Response               |
+---------------------------+
```