# Wake word models

Local ONNX files used by openWakeWord. Paths are relative to the repository root.

- `hey_pran.onnx` — custom wake phrase **Hey Pran**
- `melspectrogram.onnx` — openWakeWord audio preprocessor
- `embedding_model.onnx` — openWakeWord speech embedding

Do not point `ENGLISH_AGENT_WAKE_WORD_MODEL` at an absolute path on one machine. Use:

```bash
ENGLISH_AGENT_WAKE_WORD=hey pran
ENGLISH_AGENT_WAKE_WORD_MODEL=models/hey_pran.onnx
```

Only ONNX is used. A `.tflite` export is not loaded.
