# Acessibilidade GTA — Assistente de voz + head tracker + engine FiveM

Sistema de acessibilidade para jogar GTA RP sem depender de destreza manual.
Três subsistemas trabalhando juntos:

1. **Voz → engine FiveM**: fala comandos configuráveis (ex: "entrar no carro",
   "comer", "pegar na corda") e eles viram **chamadas nativas do GTA** via
   uma resource instalada no servidor.
2. **Modo ação (head tracker)**: liga por voz; a partir daí **rotação de cabeça
   controla a câmera do jogo** (via nativas da engine — estável) e **abrir a
   boca dispara**.
3. **Aim assist leve**: durante modo ação, a engine identifica o ped hostil
   mais próximo dentro de um cone à frente e aplica uma correção **sutil**
   na câmera. Ajuda a manter a mira sem virar aimbot.

**Requer autorização do admin da cidade** — a resource `acessibilidade_gta`
precisa ser instalada no servidor FiveM. Sem ela, nenhum comando executa.

## Como funciona

```
mic → Deepgram STT → matcher de palavras-chave (local)
                  → HTTP POST /acessibilidade_gta/command → FiveM resource
                  → client.lua: TaskEnterVehicle, SetControlNormal, etc.
                  → beep de confirmação (in-game + Windows)

[em modo ação]
webcam → MediaPipe face mesh → solvePnP → (yaw, pitch) da cabeça
       → normalização [-1..1] pela calibração pessoal de 5 poses
       → HTTP camera_set {x, y}  → tick 60Hz no client.lua
       → SetGameplayCamRelativeHeading/Pitch (rotação nativa)
       → boca aberta sustentada → HTTP shoot {hold:true}
       → client mantém RMB+LMB via SetControlNormal
       → aim assist encontra ped hostil + corrige heading suave
```

O microfone fica aberto o tempo todo. Se a sua fala contém uma das palavras-chave
configuradas, o comando correspondente é disparado e um bip curto confirma.

Quando você fala **"modo ação"**, o head tracker liga e toma controle do mouse:
virar a cabeça gira a câmera do GTA na mesma direção (cabeça reta = câmera parada),
e atirar passa a ser controlado pela sua boca — **abra pra atirar, feche pra parar**.
Fale **"desativar modo ação"** pra sair.

> **Por que head tracking e não eye tracking?** Com webcam comum, a íris é
> pequena demais no frame pra dar um olhar estável — treme muito e depende
> da postura. Já a pose da cabeça (yaw/pitch via solvePnP) é sub-grau,
> basicamente sem tremor, e é a abordagem consagrada (TrackIR/OpenTrack).
> Uma versão eye tracker foi explorada e ficou em `gaze_tracker/` como
> referência, mas o padrão do modo ação é head tracking.

## Comandos

| Comando | Palavras-chave (exemplos) | O que faz na engine |
|---|---|---|
| Entrar no carro | `entrar no carro`, `entra aí` | `TaskEnterVehicle` no carro mais próximo + liga motor + pede cinto |
| Entrar no porta-malas | `entrar porta malas`, `porta malas` | Abre porta-malas + move ped (método configurável) |
| Correr | `corre`, `correr`, `sai correndo` | Segura `INPUT_SPRINT` até mandar andar |
| Andar | `anda`, `para de correr`, `calma` | Solta `INPUT_SPRINT` |
| Pular | `pula`, `salta` | Pulso em `INPUT_JUMP` |
| Atirar | `atira`, `dispara`, `manda bala` | Rajada curta (aim + fire por 400ms) |
| **Comer** | `comer`, `come ai` | Busca comida no inventário (config por framework) e consome |
| **Beber** | `beber`, `bebe agua` | Busca bebida no inventário e consome |
| **Pegar na corda** | `pegar na corda`, `corda` | Usa corda do inventário no aliado mais próximo |
| **Modo ação (on)** | `modo ação`, `ativar modo ação` | Liga head tracker + aim assist (requer calibração na 1ª vez) |
| **Modo ação (off)** | `desativar modo ação` | Desliga tudo, solta botões |
| **Recalibrar** | `recalibrar`, `pose neutra` | Calibração de 5 poses do head tracker |

Keywords e parâmetros são editáveis em `http://127.0.0.1:8765` (UI web).

## Instalação

1. **Pré-requisitos**
   - Windows 10/11
   - Python 3.10 ou 3.11 (mediapipe tem problemas com 3.12+)
   - Conta na Deepgram ([console.deepgram.com](https://console.deepgram.com)) — plano grátis atende.
   - **Servidor FiveM com permissão pra instalar a resource** (ver abaixo).

## Instalar a resource no servidor FiveM

1. Copie a pasta `fivem_resource/acessibilidade_gta/` pra pasta `resources/` do
   seu servidor FiveM.
2. Adicione ao `server.cfg`:
   ```
   ensure acessibilidade_gta
   ```
3. Configure `fivem_resource/acessibilidade_gta/config.lua` pro seu servidor:
   - `Config.Framework` — `'qbcore'`, `'esx'` ou `'custom'`
   - `Config.FoodItems`, `Config.DrinkItems`, `Config.RopeItems` — nomes dos
     itens no seu inventário
   - `Config.TrunkMethod` — `'native'` ou `'custom'` (se seu server tem script
     de porta-malas próprio, use `'custom'` e plugue no evento
     `acessibilidade_gta:open_trunk`)
   - `Config.AimAssist.*` — range, cone, força. Os defaults já são conservadores.

O endpoint HTTP fica em `http://SEU_SERVER:30120/acessibilidade_gta/command`.
O brain Python chama esse endpoint quando você fala um comando.

2. **Configurar a chave**

   Copie `brain/.env.example` para `brain/.env` e preencha:
   ```
   DEEPGRAM_API_KEY=sua_chave_aqui
   ```

3. **Rodar**

   Dê duplo clique em `run_brain.bat`. Na primeira vez ele cria o venv e instala
   dependências (~1 min). Depois abre o navegador em `http://127.0.0.1:8765` com
   a UI de configuração e começa a ouvir o microfone.

## Configurar comandos

Abra `http://127.0.0.1:8765` no navegador. Você pode:
- Editar as palavras-chave de cada comando (uma por linha).
- Trocar a tecla usada (ex: se o seu server usa `/cinto` em vez de `B`, ajuste).
- Clicar em **Testar** pra disparar o comando agora e conferir se funciona no jogo.
- Clicar em **Salvar** pra gravar em `config/commands.json`. A próxima fala já
  usa a nova config — não precisa reiniciar.

### Teclas especiais reconhecidas

`shift`, `space`, `enter`, `tab`, `ctrl`, `alt`, `esc`, `backspace`, `up`, `down`,
`left`, `right`, `f1`–`f12`.

### Mouse

`mouse_left`, `mouse_right`, `mouse_middle`.

### Letras e números

Use só o caractere: `f`, `b`, `1`, `0`.

## Tipos de comando

| Tipo | Uso | Config |
|---|---|---|
| `tap` | Toque único | `key`, `duration_ms` |
| `multi_tap` | Várias teclas simultâneas por um tempo | `keys`, `duration_ms` |
| `hold_until` | Segura a tecla até outro comando liberar | `key`, `released_by` |
| `release` | Libera um `hold_until` em andamento | `releases` |
| `sequence` | Lista de `tap` e `wait_ms` | `steps` |

## Sobre anti-cheat

Diferente de soluções por macro, este sistema **roda como resource autorizada
do servidor**. Todas as ações são nativas do GTA disparadas legitimamente pelo
cliente do FiveM, então:

- Nenhum anti-cheat detecta — é tecnicamente indistinguível de um jogador
  usando teclado, porque as ações viram chamadas nativas do jogo (não input
  simulado do Windows).
- A resource é aberta, auditável pelo admin.
- O admin pode ajustar `Config.AimAssist.enabled = false` pra quem não permite
  aim assist mesmo pra acessibilidade.

O preço é que **precisa autorização do admin pra instalar a resource**. Em
compensação, a experiência é muito mais estável e o aim assist vira viável.

## Modo ação — como usar

1. Fale **"modo ação"**.
2. Primeira vez: tela fullscreen aparece por ~3s pedindo pra você olhar pra
   frente enquanto captura a **pose neutra**. Salva em
   `~/.head_tracker/neutral.json`.
3. A partir daí, o mouse responde à rotação da sua cabeça:
   - Cabeça **centrada** = câmera **parada**.
   - **Virou pra direita** = câmera gira pra direita (contínua, enquanto virada).
   - **Inclinou pra cima/baixo** = câmera olha pra cima/baixo.
4. **Abrir a boca por >200ms** começa a atirar (segura botão direito + esquerdo).
   **Fechar a boca por >100ms** para de atirar.
5. Fale **"desativar modo ação"** pra sair. Mouse fica liberado.
6. Se drifou (ficou achando que a "cabeça reta" é outra posição), fale
   **"recalibrar"** — novos 2s de pose neutra.

### Ajuste fino

Em [brain/modes/action_mode.py](brain/modes/action_mode.py):

- `dead_zone_deg` (padrão 3°) — ângulo abaixo do qual não há movimento. Aumente
  se o mouse se mexer "sozinho" quando você tenta ficar parado.
- `max_rotation_deg` (22°) — ângulo considerado "cabeça totalmente virada".
- `max_speed_px` (28) — pixels por tick quando ao máximo. Mais alto = câmera
  gira mais rápido. Ajuste por gosto.
- `tick_hz` (60) — frequência de update.

### Recomendações

- **Webcam na altura dos olhos**, ~50-70cm de distância.
- **Luz na sua frente**. Backlight ainda funciona melhor que no eye tracker, mas
  frontal é ótimo.
- Sem óculos escuros. Óculos comuns funcionam.

### Demos standalone

```bash
# Head tracker (usado pelo modo ação)
python -m head_tracker.demo [cam_idx]

# Eye tracker (legado, menos preciso com webcam)
python -m gaze_tracker.demo [cam_idx]
```

O demo do head tracker mostra uma cruz vermelha dentro de um alvo circular — ela
se move conforme você vira a cabeça. Serve pra validar que a detecção está
estável e que os sinais estão certos.

## Estrutura do projeto

```
ACESSIBILIDADE_GTA/
├── brain/                   # Python: voz + head tracker + bridge
│   ├── main.py              # orquestrador
│   ├── config.py            # .env loader (DEEPGRAM_API_KEY, FIVEM_BASE_URL, etc)
│   ├── speech/              # STT Deepgram (mic → texto)
│   ├── commands/
│   │   ├── registry.py      # carrega/salva commands.json
│   │   ├── matcher.py       # keyword → command_id
│   │   └── executor.py      # tipos: tap, hold, engine (→ bridge FiveM)
│   ├── bridge/
│   │   └── fivem.py         # HTTP cliente + stream de câmera
│   ├── modes/
│   │   └── action_mode.py   # head tracker → engine (câmera + aim assist)
│   ├── audio/beep.py        # bip de confirmação no Windows
│   └── web/                 # FastAPI + HTML pra editar commands.json
│
├── head_tracker/            # MÓDULO STANDALONE: rotação da cabeça (atual)
│   ├── api.py               # HeadTracker — direction normalizada [-1..1]
│   ├── demo.py              # preview com cruz de yaw/pitch
│   ├── estimator.py         # solvePnP (landmarks estáveis, sem boca)
│   └── calibration.py       # 5 poses: neutro + 4 extremos
│
├── gaze_tracker/            # MÓDULO STANDALONE: eye tracker (legado)
│   └── ...
│
├── fivem_resource/
│   └── acessibilidade_gta/  # ← INSTALAR NO SERVIDOR
│       ├── fxmanifest.lua
│       ├── config.lua       # framework, items, aim assist params
│       ├── server.lua       # HTTP handler
│       └── client.lua       # Commands + tick (camera + aim assist)
│
├── config/
│   └── commands.json        # keywords → engine actions (editável pela UI)
├── run_brain.bat
└── README.md
```

Os pacotes `head_tracker/` e `gaze_tracker/` são independentes — dá pra copiar
pra outro projeto e usar. `head_tracker` reusa o `FaceTracker`/`MouthDetector`
do `gaze_tracker` (eles servem pros dois). Ver
[`head_tracker/README.md`](head_tracker/README.md) e
[`gaze_tracker/README.md`](gaze_tracker/README.md).

## Troubleshooting

- **"mic FAIL"** — o Deepgram não conectou. Cheque se o `.env` tem `DEEPGRAM_API_KEY`
  preenchida, e se o plano não expirou.
- **Comando não dispara** — abra a UI e use **Testar** no comando para confirmar
  que a tecla está correta. O console mostra `[match] <id>` quando a fala casa.
- **Disparou mas GTA não reagiu** — dê foco no jogo antes. O Windows só entrega o
  input pra janela focada. Se estiver em modo janela, alt-tab pro GTA.
- **Tecla errada no servidor** — cada server RP usa binds diferentes pro cinto,
  ignição etc. Ajuste em `commands.json` ou pela UI. O comando "entrar no carro"
  assume F pra entrar e B pro cinto — se o seu server é diferente, mude os steps.
