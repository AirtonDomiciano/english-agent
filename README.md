run this project.
source .venv/bin/activate
python main.py

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

### Adaptive Learning Cycle

O ciclo adaptativo guarda o foco de aprendizagem sem transformar a companion em professora formal:

```text
Adaptive Learning Cycle
↓
Current Topic
↓
Learning Stage
↓
Progress
↓
Review
↓
Conversation
```

- `app/learning/cycle.py` mantém o catálogo inicial, estado persistente, progresso, revisão e atividades curtas de escrita.
- O estado fica em `data/learning_cycle.json`, ignorado pelo Git.
- `ConversationService` apenas injeta um resumo do ciclo nas instruções; ele não calcula progresso nem escolhe próximo tópico.
- Learning Modes continuam definindo comportamento; o ciclo fornece contexto.

### Daily Companion + Scheduler

As conversas iniciadas pelo agente ficam em uma camada separada:

- `app/daily/sessions.py` define `DailySession`, janelas de horário e o estado mínimo de execução diária.
- `app/daily/scheduler.py` decide quais sessões devem rodar no momento atual.
- `DailySchedulerRunner` mantém o scheduler ativo enquanto o agente está aberto no terminal.
- `app/daily/topics.py` define o formato comum `DailyTopic` e mantém o `TopicProvider` local como fallback.
- `app/daily/live_topics.py` busca assuntos recentes via RSS configurável, usa timeout, cache local em `data/live_topic_cache.json` e evita repetir títulos recentes.
- `app/daily/companion_prompt.py` contém a personalidade companion.
- `DailySession` usa o `ConversationService`, então OpenAI, memória, `PersonalContext` e Learning Modes continuam centralizados no fluxo existente.

Sessões iniciais:

- `morning`: 08:30 até 09:00.
- `afternoon`: 14:00 até 14:30.

Configurações opcionais:

- `ENGLISH_AGENT_NEWS_SEARCH_URL_TEMPLATE`: template público de RSS com `{query}`.
- `ENGLISH_AGENT_LIVE_TOPIC_CACHE`: caminho do cache local.
- `ENGLISH_AGENT_LIVE_TOPIC_TIMEOUT`: timeout da busca ao vivo.
- `ENGLISH_AGENT_LIVE_TOPIC_CACHE_TTL`: validade do cache em segundos.
- `ENGLISH_AGENT_MAX_LIVE_TOPIC_ATTEMPTS`: quantidade máxima de categorias tentadas por rodada.

### Companion Interaction Engine

A companion também possui uma camada para iniciativas espontâneas durante o dia:

- `app/companion/interactions.py` seleciona e cria interações `SOCIAL`, `RANDOM_TOPIC`, `MINI_QUIZ`, `LEARNING_RECALL`, `QUICK_CHALLENGE` e `LEARNING_COMMITMENT`.
- A engine usa `ConversationService`, `LearningCycle` e topic providers existentes; ela não chama OpenAI diretamente.
- O estado mínimo fica em `data/companion_interactions.json`, ignorado pelo Git.
- `LEARNING_COMMITMENT` usa uma janela configurável perto das 15h e pode fazer follow-ups em 10, 30, 45 e 60 minutos.
- Interações comuns respeitam períodos de silêncio e não insistem como a prática principal.

### Text-to-Speech

A saída da companion passa por um presenter central:

- `app/presentation/agent_output.py` imprime a resposta e aciona TTS quando habilitado.
- `app/speech/service.py` controla habilitação, falhas e serialização por lock para evitar duas falas simultâneas.
- `app/speech/providers/openai_tts.py` é o provider neural, usando OpenAI TTS (`gpt-4o-mini-tts`) e o dispositivo de áudio padrão.
- `app/speech/providers/espeak.py` permanece disponível como provider local e fallback automático.

A resposta continua aparecendo no terminal e depois é falada. Falha no TTS não interrompe a conversa. Se o provider neural falhar, o agente tenta o eSpeak.

No Debian, instale o player local e o fallback:

```bash
sudo apt install alsa-utils espeak
```

Selecionar o provider:

```bash
ENGLISH_AGENT_TTS_PROVIDER=openai
```

```bash
ENGLISH_AGENT_TTS_PROVIDER=espeak
```

Selecionar voz e modelo do provider neural:

```bash
ENGLISH_AGENT_TTS_MODEL=gpt-4o-mini-tts
ENGLISH_AGENT_TTS_VOICE=coral
```

Vozes comuns: `coral`, `nova`, `alloy`, `sage`, `marin`, `cedar`.

Configuração:

- `ENGLISH_AGENT_TTS_ENABLED=true` habilita voz.
- `ENGLISH_AGENT_TTS_ENABLED=false` ou ausente mantém apenas texto.
- `ENGLISH_AGENT_TTS_PROVIDER=openai` seleciona a voz neural.
- `ENGLISH_AGENT_TTS_PROVIDER=espeak` volta para o eSpeak.
- `ENGLISH_AGENT_TTS_MODEL=gpt-4o-mini-tts` define o modelo neural.
- `ENGLISH_AGENT_TTS_VOICE=coral` define a voz do provider OpenAI.
- `ENGLISH_AGENT_TTS_COMMAND=espeak` permite trocar o comando do eSpeak, por exemplo `espeak-ng`.
- `ENGLISH_AGENT_TTS_PLAY_COMMAND=aplay -q` reproduz o arquivo gerado no dispositivo padrão, sem hardcode de saída e sem mensagens técnicas do player.
- `ENGLISH_AGENT_TTS_TIMEOUT=30` controla o timeout de geração e reprodução.

Para testar:

```bash
python main.py
```

Envie uma mensagem. O texto aparece no terminal e, em seguida, a resposta é falada.

Para voltar ao eSpeak:

```bash
ENGLISH_AGENT_TTS_PROVIDER=espeak
```

### Speech-to-Text

A entrada por voz fica separada da conversa:

- `app/voice/controller.py` orquestra um turno `/voice` com estado explícito: `IDLE` → `LISTENING` → `TRANSCRIBING` → `THINKING` → `SPEAKING` → `IDLE`.
- Enquanto o agente está em `SPEAKING`, ele não entra em `LISTENING`. Uma segunda sessão de voz é recusada até o turno voltar para `IDLE`.
- `app/speech/recognition_service.py` continua responsável só por captura e transcrição.
- `app/speech/audio.py` captura uma frase do microfone usando `arecord` e salva um WAV temporário.
- `app/speech/recognition_providers/openai_transcription.py` é o provider inicial, usando OpenAI transcription com modelo configurável.
- `ConversationService` continua recebendo apenas texto; ele não conhece microfone nem provider de STT.
- `AgentOutputPresenter` continua sendo o ponto central de saída, então a resposta transcrita também pode acionar TTS.

No Debian, instale o capturador local:

```bash
sudo apt install alsa-utils
```

Configuração:

- `ENGLISH_AGENT_STT_ENABLED=true` habilita o comando de voz.
- `ENGLISH_AGENT_STT_ENABLED=false` ou ausente mantém apenas digitação.
- `ENGLISH_AGENT_STT_PROVIDER=openai` seleciona o provider atual.
- `ENGLISH_AGENT_STT_LANGUAGE=en` define o idioma esperado da fala.
- `ENGLISH_AGENT_STT_MODEL=whisper-1` define o modelo de transcrição.
- `ENGLISH_AGENT_STT_TIMEOUT=30` controla o timeout da chamada externa.
- `ENGLISH_AGENT_STT_DURATION_SECONDS=5` controla o tempo de gravação de cada frase.
- `ENGLISH_AGENT_STT_RECORD_COMMAND=arecord` permite trocar o comando de captura.
- `ENGLISH_AGENT_STT_AUDIO_DIR=/tmp` permite trocar a pasta de áudio temporário.

Para testar manualmente:

```bash
python main.py
```

Depois digite:

```bash
/voice
```

O agente mostra `Listening...`, grava uma frase, exibe a transcrição como `You: ...`, envia para a conversa e responde pelo fluxo normal de texto/TTS.

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
