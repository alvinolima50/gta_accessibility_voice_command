-- ==========================================================================
-- CONFIG DO RESOURCE DE ACESSIBILIDADE
-- Todos os ajustes que dependem DO SERVIDOR RP moram aqui.
-- O admin da cidade vai mexer principalmente em:
--   * Framework (QBCore / ESX / Custom)
--   * Nomes de itens do inventário pra comida e corda
--   * Exports pra "abrir porta-malas" (varia entre scripts)
-- ==========================================================================

Config = {}

-- ---------------------------------------------------------------------------
-- FRAMEWORK
-- ---------------------------------------------------------------------------
-- 'qbcore' | 'esx' | 'custom' | 'mock'
-- 'mock' = modo teste sem framework. Comandos de inventário (comer/beber/corda)
--          fingem que funcionaram e notificam no chat — serve pra testar em
--          servers vanilla sem precisar instalar QBCore/ESX.
-- 'custom' = delega TUDO pra eventos que o admin conecta no script dele.
Config.Framework = 'mock'

-- ---------------------------------------------------------------------------
-- INPUT (SetControlNormal)
-- IDs do GTA V que representam ações do player. Não precisa mudar na maioria
-- dos servers (são as teclas "virtuais" default).
-- ---------------------------------------------------------------------------
Config.Controls = {
    sprint      = 21,   -- shift
    jump        = 22,   -- space
    aim         = 25,   -- botão direito
    fire        = 24,   -- botão esquerdo
    enter_veh   = 23,   -- F
}

-- ---------------------------------------------------------------------------
-- CÂMERA (head tracker → rotação da câmera do jogo)
-- ---------------------------------------------------------------------------
Config.Camera = {
    -- Graus por segundo quando a cabeça está no extremo (x=±1 / y=±1).
    -- Valor maior = rotação mais agressiva, recomendado 90-180.
    max_yaw_per_sec   = 140.0,
    max_pitch_per_sec = 90.0,

    -- Limites absolutos de pitch (evita ir pra cabeça pra baixo).
    pitch_min_deg = -60.0,
    pitch_max_deg =  60.0,
}

-- ---------------------------------------------------------------------------
-- AIM ASSIST (aimbot leve)
-- "Trava suave": quando você está atirando e há um ped humano no raio, a
-- câmera corrige MUITO devagar em direção à cabeça dele. Não resolve a mira
-- — ajuda a manter.
-- ---------------------------------------------------------------------------
Config.AimAssist = {
    enabled             = true,     -- liga/desliga sem recompile
    max_distance        = 25.0,     -- em metros
    cone_half_angle_deg = 10.0,     -- só ativa se o alvo está DENTRO desse cone à frente
    pull_strength       = 0.08,     -- 0..1 — quanto da distância até o alvo é corrigida por tick
                                    -- (0.08 a 60Hz = correção sutil, ~5deg/s na vizinhança do alvo)
    max_correction_per_sec = 6.0,   -- graus/s — teto pra não parecer aimbot
    require_aiming_button  = true,  -- só ativa quando RMB (controle 25) está pressionado
    target_bone            = 31086, -- bone tag SKEL_Head
    ignore_friendly        = true,  -- ignora members do mesmo relationship group
}

-- ---------------------------------------------------------------------------
-- COMIDA / BEBIDA (inventário)
-- Lista em ORDEM DE PRIORIDADE. O comando "comer" tenta o primeiro item na
-- mochila. Se não tiver, tenta o segundo, etc.
-- Formato: nome do item no inventário do server.
-- ---------------------------------------------------------------------------
Config.FoodItems  = { 'sandwich', 'burger', 'hotdog', 'tosta', 'sandwich_basic' }
Config.DrinkItems = { 'water', 'water_bottle', 'soda', 'juice', 'coffee' }

-- ---------------------------------------------------------------------------
-- CORDA (pra pegar aliado na corda)
-- ---------------------------------------------------------------------------
Config.RopeItems = { 'rope', 'corda' }

-- Raio máximo (m) pra considerar "um aliado próximo" quando falar "pegar na corda"
Config.RopeGrabRadius = 3.0

-- ---------------------------------------------------------------------------
-- PORTA-MALAS
-- Dependendo do servidor, entrar no porta-malas usa evento/export diferente.
-- 'native' = só abre e manda entrar (funciona em servers simples).
-- 'qb-trunk', 'esx-trunk', 'custom' = chama exports específicos.
-- ---------------------------------------------------------------------------
Config.TrunkMethod = 'native'

-- Raio máximo (m) pra considerar "carro perto" pros comandos enter_vehicle e enter_trunk.
Config.VehicleSearchRadius = 5.0

-- ---------------------------------------------------------------------------
-- EVENTOS CUSTOMIZADOS (quando Framework = 'custom')
-- O admin pode plugar esses eventos no script dele pra executar o que o
-- server usa internamente pra "consumir" um item.
--   TriggerEvent(Config.Events.consume, itemName)
--   TriggerEvent(Config.Events.use_rope)
-- ---------------------------------------------------------------------------
Config.Events = {
    consume   = 'acessibilidade_gta:consume_item',    -- (itemName)
    use_rope  = 'acessibilidade_gta:use_rope',        -- (targetServerId | nil)
    open_trunk = 'acessibilidade_gta:open_trunk',     -- (vehicleNetId)
}

-- ---------------------------------------------------------------------------
-- BEEP DE CONFIRMAÇÃO (client-side, som nativo do jogo)
-- Toca um SFX curto pro jogador quando a ordem é recebida. Útil pra quem
-- quer confirmação in-game além do beep do Windows.
-- ---------------------------------------------------------------------------
Config.Beep = {
    enabled = true,
    sound   = 'SELECT',     -- nome do som
    set     = 'HUD_FRONTEND_DEFAULT_SOUNDSET',
}
