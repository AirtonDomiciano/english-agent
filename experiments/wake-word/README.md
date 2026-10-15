# Wake Word POC — Hey Pran

Experimento isolado para provar detecção local de **Hey Pran** no Debian.
Não inicia o English Agent, STT, TTS nem sessão de voz.

## O que este experimento reaproveita

- `ArecordFrameSource` (`app/voice/wake_word_providers/openwakeword.py`): stream PCM 16 kHz, mono, S16_LE
- `openwakeword.Model` com `inference_framework="onnx"` (já usado pelo Agent)
- `onnxruntime` e `numpy` do `requirements.txt`

O fluxo de produção (`WakeWordService`, `VoiceConversationController`, `VoiceConversationSession`) **não é chamado**.

## Dependências

Do diretório raiz do projeto:

```bash
pip install -r requirements.txt
pip install openwakeword==0.6.0 --no-deps
sudo apt install alsa-utils
```

O `--no-deps` é necessário no Python 3.13 porque `tflite-runtime` não tem wheel. A detecção usa ONNX.

Na primeira carga, o openWakeWord pode baixar os modelos de *embedding* (melspectrogram/embedding) para o cache local. A detecção em si não usa API externa.

## Modelo

O Agent já inclui o modelo em:

```text
models/hey_pran.onnx
```

Sem ele, o script sai com:

```text
Wake word model not found:
models/hey_pran.onnx
```

Não use um modelo de outra frase (`hey_jarvis`, etc.) neste caminho. Ele só acorda com a frase para a qual foi treinado.

Como gerar `hey_pran.onnx`: notebook oficial do openWakeWord, com:

```yaml
model_name: "hey_pran"
target_phrase:
  - "hey pran"
```

## Como executar

Na raiz do repositório:

```bash
python experiments/wake-word/test_microphone.py
```

Threshold (teste 0.5, 0.6, 0.7, 0.8, 0.9 sem mudar código):

```bash
WAKE_WORD_THRESHOLD=0.75 python experiments/wake-word/test_microphone.py
```

Outras variáveis:

| Variável | Default | Função |
|---|---|---|
| `WAKE_WORD_THRESHOLD` | `0.5` | Score mínimo para detectar |
| `WAKE_WORD_COOLDOWN_SECONDS` | `2` | Evita várias detecções da mesma fala |
| `WAKE_WORD_SCORE_PRINT_THRESHOLD` | `0.2` | Só imprime score de diagnóstico acima disso |
| `WAKE_WORD_MODEL` | `models/hey_pran.onnx` | Caminho do ONNX |

## Formato de áudio

O detector recebe o mesmo formato do openWakeWord em produção:

- 16000 Hz
- 1 canal
- PCM signed 16-bit little-endian (`S16_LE`)
- 1280 samples por frame (80 ms)
- captura contínua via `arecord` (não o WAV de 5 s do STT)

Não rode `python main.py` ao mesmo tempo: os dois usariam o mesmo microfone.

## Como interpretar

```text
🎤 Listening...
score=0.23
score=0.41
score=0.87
🔥 WAKE WORD DETECTED
```

- Scores baixos e estáveis: ambiente, não é a frase.
- Subida clara + `WAKE WORD DETECTED`: o modelo aceitou **Hey Pran**.
- Várias detecções da mesma fala: suba o threshold ou o cooldown.
- Nenhuma detecção ao falar a frase: baixe o threshold ou o modelo não é de "hey pran".

Scores abaixo de `0.2` não são impressos, para não poluir o terminal.

## Encerrar

`Ctrl+C`. O script para o `arecord` no `finally` (terminate, depois kill se precisar).

## Limitações

- POC: não liga o Agent.
- Sem o ONNX customizado, não há o que detectar.
- "Pran" sozinho pode não passar; a frase treinada é **Hey Pran**.
- Sem barge-in, AEC ou speaker recognition.
- TTS do Agent no mesmo microfone pode gerar falso positivo; isso é um dos testes manuais, não um bug desta POC.
- openWakeWord 0.6.0 no Python 3.13 continua sendo instalado com `--no-deps`.
