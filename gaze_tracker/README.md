# gaze_tracker

Eye tracker com webcam baseado em MediaPipe Face Mesh + Iris.
Entrega, em tempo real:
- Ponto de olhar `(x, y)` na tela, calibrado.
- Eventos de abertura/fechamento de boca (para gatilhos gestuais).

**Sem hardware dedicado** — qualquer webcam comum funciona. Pacote 100% Python,
sem dependência de serviços externos.

## Instalar

```bash
pip install -r requirements.txt
```

Python 3.10 ou 3.11 é o mais compatível com `mediapipe` no momento.

## Uso rápido

```python
from gaze_tracker import GazeTracker

gt = GazeTracker()
gt.run_calibration()        # overlay fullscreen 9 pontos, ~18s
gt.start()                  # inicia loop de webcam em background

def on_mouth(is_open: bool):
    print("boca", "aberta" if is_open else "fechada")

gt.set_mouth_callback(on_mouth)

while True:
    g = gt.get_gaze()
    if g:
        print(f"olhando em {g.x:.0f}, {g.y:.0f}  confiança={g.confidence:.2f}")
```

## Demo

```bash
python -m gaze_tracker.demo
```

Abre uma janela de preview com:
- O frame da webcam com landmarks de íris e boca desenhados.
- Um ponto verde na tela onde ele estima que você está olhando.
- Estado da boca (aberta/fechada).
- Atalho: `C` recalibra, `ESC` sai.

## Arquitetura

```
gaze_tracker/
├── api.py              # GazeTracker — API pública
├── demo.py             # preview standalone
├── core/
│   ├── tracker.py      # webcam + MediaPipe Face Mesh + Iris
│   ├── gaze_estimator.py  # extrai features (iris + head pose)
│   ├── screen_mapper.py   # polinomial: features -> (x, y) na tela
│   ├── mouth.py        # MAR + histerese + hold time
│   └── filters.py      # One Euro filter (suaviza jitter)
└── calibration/
    ├── calibrator.py   # coleta amostras + ajusta modelo
    └── overlay.py      # janela fullscreen com pontos-alvo
```

## Como lida com movimento da cabeça

Três camadas combinadas:

1. **Compensação por head pose** — o estimador usa, além da posição da íris no
   olho, o `yaw` e `pitch` da cabeça (via `cv2.solvePnP` com os landmarks 3D
   canônicos do MediaPipe). O modelo aprende `(iris_x, iris_y, yaw, pitch) →
   (screen_x, screen_y)`, então movimento de cabeça já é entrada do modelo — não
   é ruído.
2. **Filtro One Euro** — suprime jitter da íris com cutoff adaptativo. Em repouso
   suaviza forte; em movimento rápido responde rápido.
3. **Recalibração por voz** — se a pessoa trocar de posição na cadeira, basta
   dizer "recalibrar" (ou chamar `gt.run_calibration(quick=True)`) pra um ajuste
   de 5 pontos em ~8s.

## Calibração

- **Completa (9 pontos)**: primeira vez que usa. ~18s.
- **Rápida (5 pontos)**: ajuste depois de trocar de posição. ~8s.

A calibração é salva em `~/.gaze_tracker/calibration.json`. Pode ser apagada pra
forçar uma nova.

## Limites honestos

- Precisão típica: **3–5° de ângulo visual**. Em tela 24" a 60cm, isso é ~3-6cm
  de erro. **Não é Tobii.** Serve bem pra "travar alvo num raio razoável",
  não pra mira precisa de sniper.
- Iluminação frontal é essencial. Contra-luz (janela atrás da pessoa) quebra o
  tracker.
- Óculos comuns funcionam. Óculos escuros não.
- Webcam deve ficar **na altura dos olhos** e ~50-70cm de distância.
