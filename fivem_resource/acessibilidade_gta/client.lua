-- ==========================================================================
-- CLIENT — executor das ordens vindas do brain via server.lua
-- Recebe eventos `acessibilidade_gta:command` com { action = "...", ... }
-- e dispara a nativa/lógica correspondente.
-- ==========================================================================

local function log(msg)
    print('[acessibilidade_gta] ' .. msg)
end

-- --------------------------------------------------------------------------
-- Estado mutável controlado pelo tick
-- --------------------------------------------------------------------------
local State = {
    sprinting = false,
    firing    = false,
    aiming    = false,
    sprint_debug_ms = 0,

    -- Head tracker
    cam_x = 0.0,
    cam_y = 0.0,
    cam_active = false,

    aim_assist_on = false,
}

-- --------------------------------------------------------------------------
-- HELPERS GERAIS
-- --------------------------------------------------------------------------
local function playBeep()
    if Config.Beep.enabled then
        PlaySoundFrontend(-1, Config.Beep.sound, Config.Beep.set, true)
    end
end

local function getClosestVehicle(radius)
    local ped = PlayerPedId()
    local pos = GetEntityCoords(ped)
    local veh, closestDist = nil, radius + 1
    -- Vamos iterar pelos veículos num raio pequeno via native GetGamePool
    local pool = GetGamePool('CVehicle')
    for _, v in ipairs(pool) do
        if DoesEntityExist(v) then
            local d = #(GetEntityCoords(v) - pos)
            if d < closestDist then
                veh = v
                closestDist = d
            end
        end
    end
    if veh and closestDist <= radius then return veh, closestDist end
    return nil, nil
end

local function getClosestHostilePed()
    local ped = PlayerPedId()
    local pos = GetEntityCoords(ped)
    local fwd = GetEntityForwardVector(ped)

    local maxD  = Config.AimAssist.max_distance
    local cone  = math.rad(Config.AimAssist.cone_half_angle_deg)
    local best, bestScore = nil, -1.0

    for _, p in ipairs(GetGamePool('CPed')) do
        if p ~= ped and DoesEntityExist(p) and not IsPedDeadOrDying(p, true)
           and IsPedHuman(p) then
            -- Evita aliados (relationship friendly) se configurado
            local skip = false
            if Config.AimAssist.ignore_friendly then
                local rel = GetRelationshipBetweenPeds(ped, p)
                -- 0=COMPANION 1=RESPECT 2=LIKE 3=NEUTRAL 4=DISLIKE 5=HATE
                if rel <= 2 then skip = true end
            end
            if not skip then
                local tp = GetPedBoneCoords(p, Config.AimAssist.target_bone, 0.0, 0.0, 0.0)
                local d = #(tp - pos)
                if d < maxD then
                    -- Ângulo entre fwd e direção até alvo
                    local dir = tp - pos
                    local len = #(vector3(dir.x, dir.y, 0.0))
                    if len > 0.01 then
                        local n = vector3(dir.x/len, dir.y/len, 0.0)
                        local fx = vector3(fwd.x, fwd.y, 0.0)
                        local fl = #(fx) + 1e-6
                        local fxn = vector3(fx.x/fl, fx.y/fl, 0.0)
                        local dot = n.x*fxn.x + n.y*fxn.y
                        local ang = math.acos(math.max(-1.0, math.min(1.0, dot)))
                        if ang < cone then
                            -- Score: prioriza peds mais próximos e mais centrais
                            local score = (1.0 - ang/cone) * (1.0 - d/maxD)
                            if score > bestScore then
                                bestScore = score
                                best = { ped = p, pos = tp, dist = d, angle = ang }
                            end
                        end
                    end
                end
            end
        end
    end
    return best
end

-- --------------------------------------------------------------------------
-- INVENTORY ADAPTERS
-- Tentamos detectar framework. Se falhar, disparamos evento custom pro admin.
-- Em 'mock', simulamos sucesso com notificação no chat — usado pra teste em
-- server vanilla sem inventário.
-- --------------------------------------------------------------------------
local function chatNotify(msg)
    TriggerEvent('chat:addMessage', {
        args = { 'acessibilidade', msg },
        color = { 120, 180, 255 },
    })
end

local function hasItem(itemName)
    local fw = Config.Framework
    if fw == 'qbcore' then
        local QBCore = exports['qb-core'] and exports['qb-core']:GetCoreObject()
        if not QBCore then return nil, 'qb-core not found' end
        local pd = QBCore.Functions.GetPlayerData()
        for _, it in pairs(pd.items or {}) do
            if it.name == itemName and (it.amount or 0) > 0 then return true end
        end
        return false
    elseif fw == 'esx' then
        local ESX = exports['es_extended'] and exports['es_extended']:getSharedObject()
        if not ESX then return nil, 'es_extended not found' end
        local pd = ESX.GetPlayerData()
        for _, it in pairs(pd.inventory or {}) do
            if it.name == itemName and (it.count or 0) > 0 then return true end
        end
        return false
    elseif fw == 'mock' then
        return true  -- sempre finge ter
    end
    -- custom: não temos acesso ao inventário. Retorna nil = "não sei".
    return nil, 'custom framework — admin handles'
end

local function consumeItem(itemName)
    local fw = Config.Framework
    if fw == 'qbcore' then
        TriggerServerEvent('QBCore:Server:UseItem', { name = itemName })
        return true
    elseif fw == 'esx' then
        TriggerServerEvent('esx:useItem', itemName)
        return true
    elseif fw == 'mock' then
        -- Finge que usou. Útil pra teste.
        chatNotify(('[MOCK] consumiu %s'):format(itemName))
        return true
    else
        TriggerEvent(Config.Events.consume, itemName)
        TriggerServerEvent(Config.Events.consume, itemName)
        return true
    end
end

local function findAndConsumeFromList(list, label)
    for _, item in ipairs(list) do
        local has, err = hasItem(item)
        if has == true then
            log(('%s: usando item %s'):format(label, item))
            consumeItem(item)
            return true
        end
        if has == nil then
            -- framework custom: a gente não sabe; tenta o primeiro e deixa
            -- o admin filtrar.
            log(('%s: framework custom — tentando %s'):format(label, item))
            consumeItem(item)
            return true
        end
    end
    log(label .. ': nenhum item encontrado no inventário')
    chatNotify(label .. ': sem item no inventário')
    return false
end

-- --------------------------------------------------------------------------
-- COMMANDS TABLE
-- Cada chave = action string. Valor = função(data) -> void.
-- --------------------------------------------------------------------------
local Commands = {}

-- ----- INPUT TOGGLES -------------------------------------------------------
-- Sprint = literalmente segurar Shift. Tick repressiona INPUT_SPRINT a cada
-- frame. Nada mais — não mexe em stamina nem multiplicadores, que interferem
-- com o estado normal de movimento do player.
function Commands.sprint_start()
    log('sprint_start')
    State.sprinting = true
end

function Commands.sprint_stop()
    log('sprint_stop')
    State.sprinting = false
end

function Commands.jump()
    log('jump')
    local ped = PlayerPedId()
    -- TaskJump é mais confiável que tentar simular INPUT_JUMP — pula direto
    -- independente de estado de input do jogo.
    TaskJump(ped, true, false, false)
end

-- Atirar em rajada curta (boca aberta por pouco tempo) OU toggle contínuo.
-- Se data.hold == true → toggle on. Se data.hold == false → toggle off.
-- Se data.hold == nil → rajada de duration_ms (default 400).
function Commands.shoot(data)
    data = data or {}
    if data.hold == true then
        log('shoot ON (hold)')
        State.firing = true
        State.aiming = true
        return
    end
    if data.hold == false then
        log('shoot OFF')
        State.firing = false
        State.aiming = false
        return
    end
    local dur = tonumber(data.duration_ms) or 400
    log('shoot burst ' .. dur .. 'ms')
    CreateThread(function()
        State.firing = true
        State.aiming = true
        Wait(dur)
        State.firing = false
        State.aiming = false
    end)
end

-- ----- VEHICLE -------------------------------------------------------------
function Commands.enter_vehicle()
    log('enter_vehicle')
    local ped = PlayerPedId()
    local veh, dist = getClosestVehicle(Config.VehicleSearchRadius)
    if not veh then
        log('enter_vehicle: nenhum carro dentro de '..Config.VehicleSearchRadius..'m')
        return
    end
    log(('enter_vehicle: carro a %.1fm'):format(dist))
    -- -1 = motorista. 5000ms timeout. 2.0 = velocidade pra chegar. 1 = flag driver.
    TaskEnterVehicle(ped, veh, 5000, -1, 2.0, 1, 0)
    -- Depois que entrar, ligar motor (nem todo framework faz automático).
    CreateThread(function()
        local t0 = GetGameTimer()
        while GetGameTimer() - t0 < 6000 do
            if IsPedInVehicle(ped, veh, false) then
                SetVehicleEngineOn(veh, true, true, false)
                -- Cinto varia MUITO por server — mandamos evento pro script do server.
                TriggerEvent('acessibilidade_gta:request_seatbelt')
                return
            end
            Wait(100)
        end
    end)
end

function Commands.enter_trunk()
    log('enter_trunk')
    local ped = PlayerPedId()
    local veh, dist = getClosestVehicle(Config.VehicleSearchRadius)
    if not veh then
        log('enter_trunk: nenhum carro perto')
        return
    end
    log(('enter_trunk: carro a %.1fm via método=%s'):format(dist, Config.TrunkMethod))
    local method = Config.TrunkMethod or 'native'
    if method == 'native' then
        -- Abre porta-malas, teleporta o player pro assento passageiro fantasma
        -- do porta-malas (não é 100% fiel; muitos servers têm script próprio).
        SetVehicleDoorOpen(veh, 5, false, false)
        -- Assento -2 no GTA V algumas vezes corresponde ao porta-malas em mods.
        -- Se falhar, o admin precisa configurar TrunkMethod='custom'.
        local trunkSeat = -2
        SetPedIntoVehicle(ped, veh, trunkSeat)
        AttachEntityToEntity(ped, veh, GetEntityBoneIndexByName(veh, 'boot'),
                             0.0, -0.5, 0.3, 0.0, 0.0, 0.0, false, false, false, false, 2, true)
    else
        -- Delega ao script do server
        local netId = VehToNet(veh)
        TriggerEvent(Config.Events.open_trunk, netId)
        TriggerServerEvent(Config.Events.open_trunk, netId)
    end
end

-- ----- INVENTORY: COMER / BEBER -------------------------------------------
function Commands.eat()
    log('eat (framework=' .. Config.Framework .. ')')
    findAndConsumeFromList(Config.FoodItems, 'comer')
end

function Commands.drink()
    log('drink (framework=' .. Config.Framework .. ')')
    findAndConsumeFromList(Config.DrinkItems, 'beber')
end

-- ----- CORDA ---------------------------------------------------------------
function Commands.use_rope()
    log('use_rope (framework=' .. Config.Framework .. ')')
    -- Verifica item
    local has = false
    for _, item in ipairs(Config.RopeItems) do
        local r = hasItem(item)
        if r == true or r == nil then has = true; break end
    end
    if not has then
        log('use_rope: sem corda no inventário')
        chatNotify('sem corda no inventário')
        return
    end
    if Config.Framework == 'mock' then
        chatNotify('[MOCK] puxou corda')
    end

    -- Encontra aliado mais próximo (qualquer jogador visível num raio)
    local ped = PlayerPedId()
    local pos = GetEntityCoords(ped)
    local target, bestD = nil, Config.RopeGrabRadius + 1
    for _, p in ipairs(GetGamePool('CPed')) do
        if p ~= ped and DoesEntityExist(p) and IsPedAPlayer(p) then
            local d = #(GetEntityCoords(p) - pos)
            if d < bestD then target, bestD = p, d end
        end
    end
    local targetSrc = nil
    if target then
        local playerIdx = NetworkGetPlayerIndexFromPed(target)
        if playerIdx ~= -1 then
            targetSrc = GetPlayerServerId(playerIdx)
        end
    end
    -- Manda o evento pra server com o serverId do alvo (se houver)
    TriggerEvent(Config.Events.use_rope, targetSrc)
    TriggerServerEvent(Config.Events.use_rope, targetSrc)
end

-- ----- HEAD TRACKER: CÂMERA ------------------------------------------------
-- Brain manda (x, y) normalizados em [-1,1] representando direção da cabeça.
-- Tick interpreta como velocidade de rotação da câmera.
function Commands.camera_set(data)
    -- Silencioso — esse é chamado 30x/s. Não loga.
    State.cam_x = tonumber(data.x) or 0.0
    State.cam_y = tonumber(data.y) or 0.0
    State.cam_active = true
end

function Commands.camera_stop()
    log('camera_stop')
    State.cam_x = 0.0
    State.cam_y = 0.0
    State.cam_active = false
end

-- ----- AIM ASSIST ----------------------------------------------------------
function Commands.aim_assist_on()
    log('aim_assist_on (enabled=' .. tostring(Config.AimAssist.enabled) .. ')')
    State.aim_assist_on = Config.AimAssist.enabled
end

function Commands.aim_assist_off()
    log('aim_assist_off')
    State.aim_assist_on = false
end

-- ----- HEALTH CHECK / DEBUG -----------------------------------------------
function Commands.ping()
    log('ping OK')
    playBeep()
end

-- --------------------------------------------------------------------------
-- EVENT LISTENER — dispatcher
-- --------------------------------------------------------------------------
-- Ações de alta frequência que NÃO devem tocar beep (spam).
local SILENT_ACTIONS = { camera_set = true }

RegisterNetEvent('acessibilidade_gta:command', function(data)
    local act = data and data.action
    local fn = act and Commands[act]
    if not fn then
        log('comando desconhecido: ' .. tostring(act))
        return
    end
    local ok, err = pcall(fn, data)
    if not ok then
        log('erro em ' .. act .. ': ' .. tostring(err))
    elseif not SILENT_ACTIONS[act] then
        playBeep()
    end
end)

-- --------------------------------------------------------------------------
-- TICK — aplica estados contínuos (sprint, firing, câmera, aim assist)
-- --------------------------------------------------------------------------
CreateThread(function()
    while true do
        Wait(0)  -- roda todo frame

        local ped = PlayerPedId()

        -- Sprint contínuo: apenas mantém Shift pressionado enquanto State.sprinting.
        -- Player precisa estar se movendo (W segurado) pra ter efeito.
        if State.sprinting then
            SetControlNormal(0, Config.Controls.sprint, 1.0)
        end
        -- Fire / aim contínuo (boca aberta)
        if State.firing then
            SetControlNormal(0, Config.Controls.fire, 1.0)
            SetControlNormal(0, Config.Controls.aim, 1.0)
        elseif State.aiming then
            SetControlNormal(0, Config.Controls.aim, 1.0)
        end

        -- Câmera via head tracker
        if State.cam_active then
            local dt = GetFrameTime()
            -- x positivo = olhou pra direita → heading precisa DIMINUIR (GTA convention)
            local dyaw   = -State.cam_x * Config.Camera.max_yaw_per_sec   * dt
            local dpitch = -State.cam_y * Config.Camera.max_pitch_per_sec * dt

            local curH = GetGameplayCamRelativeHeading()
            SetGameplayCamRelativeHeading(curH + dyaw)

            local curP = GetGameplayCamRelativePitch()
            local newP = math.max(Config.Camera.pitch_min_deg,
                           math.min(Config.Camera.pitch_max_deg, curP + dpitch))
            SetGameplayCamRelativePitch(newP, 1.0)
        end

        -- Aim assist
        if State.aim_assist_on then
            local canRun = true
            if Config.AimAssist.require_aiming_button then
                canRun = IsControlPressed(0, Config.Controls.aim)
                         or State.firing or State.aiming
            end
            if canRun then
                local target = getClosestHostilePed()
                if target then
                    local pedPos = GetPedBoneCoords(ped, 31086, 0.0, 0.0, 0.0)
                    local dir = target.pos - pedPos
                    -- Direção desejada em yaw absoluto
                    local desiredH = math.deg(math.atan2(-dir.x, dir.y))
                    local currentH = GetEntityHeading(ped) + GetGameplayCamRelativeHeading()
                    local deltaH = desiredH - currentH
                    -- Normaliza pra [-180..180]
                    while deltaH > 180 do deltaH = deltaH - 360 end
                    while deltaH < -180 do deltaH = deltaH + 360 end

                    -- Pull proporcional mas saturado
                    local pull = deltaH * Config.AimAssist.pull_strength
                    local maxStep = Config.AimAssist.max_correction_per_sec * GetFrameTime()
                    if pull >  maxStep then pull =  maxStep end
                    if pull < -maxStep then pull = -maxStep end

                    SetGameplayCamRelativeHeading(GetGameplayCamRelativeHeading() + pull)
                end
            end
        end
    end
end)

log('client carregado.')
