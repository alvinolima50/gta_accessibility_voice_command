# head_tracker

Controla câmera por **rotação de cabeça** — a abordagem que o TrackIR/AITrack/
OpenTrack usam há 20 anos em simuladores de voo. Muito mais estável que eye
tracking em webcam, porque `solvePnP` com os landmarks do MediaPipe dá head pose
precisa a sub-grau, sem o tremor da íris.

Mantém o **detector de boca** do `gaze_tracker` pra gatilhos gestuais (abrir =
atirar, fechar = parar).

## Por que head tracking em vez de eye tracking

| | Eye tracking (íris) | Head tracking (esta abordagem) |
|---|---|---|
| Estabilidade | Tremor constante de 1-3° | Sub-grau, praticamente sem tremor |
| Sensível a iluminação | Sim, muito | Pouco |
| Sensível a postura | Muito — recalibra se mexer | Imune — é relativo à pose neutra |
| Calibração | 9 pontos, ~18s | 1 ponto, 2s |
| "Feel" em FPS | Artificial, impreciso | Natural, como TrackIR |

## Uso rápido

```python
from head_tracker import HeadTracker

ht = HeadTracker(camera_index=0)
ht.start()
ht.capture_neutral()          # 2s olhando pra frente pra marcar pose neutra

while True:
    d = ht.get_direction()
    if d:
        print(f"Δyaw={d.dyaw_deg:+.1f}°  Δpitch={d.dpitch_deg:+.1f}°")
```

## Demo standalone

```bash
python -m head_tracker.demo
```

Mostra preview da webcam com uma cruz vermelha indicando yaw/pitch atual
relativos à neutra, barras em `±30°` e estado da boca. Atalhos:

- `N` — recaptura pose neutra (se saiu da posição)
- `ESC` — sai

## Arquitetura

```
head_tracker/
├── api.py              # HeadTracker — API pública
├── demo.py             # preview standalone
├── estimator.py        # head pose → ângulos relativos à neutra
├── calibration.py      # captura pose neutra (2s)
└── requirements.txt
```

Reusa do `gaze_tracker`:
- `gaze_tracker.core.tracker.FaceTracker`   — webcam + MediaPipe
- `gaze_tracker.core.mouth.MouthDetector`   — MAR + histerese
- `gaze_tracker.core.filters.OneEuroFilter` — suavização

## Como gerar movimento de mouse a partir do head tracking

O consumidor (ex: `action_mode.py`) faz:

```python
dyaw = direction.dyaw_deg   # negativo = cabeça virada pra direita do jogador
dpitch = direction.dpitch_deg

# Dead zone + ganho
if abs(dyaw) < 3.0: dyaw = 0
if abs(dpitch) < 3.0: dpitch = 0

mouse_dx = -dyaw * SENSITIVITY   # sinal depende da convenção do solvePnP
mouse_dy = dpitch * SENSITIVITY
mouse.move(mouse_dx, mouse_dy)
```

Chamado em loop de 30Hz — camera do GTA vai rotacionar continuamente enquanto
você mantém a cabeça virada.
