-- Comandos só de DEV. Sem checagem de permissão — NÃO usar em produção.
-- No server de teste local, chame pelo chat:
--   /car adder          → spawna um adder ao seu lado
--   /car sultan         → spawna sultan
--   /dv                 → apaga o carro que você está dentro (ou o mais próximo)
--   /weapon weapon_pistol 250   → dá arma com 250 balas
--   /heal               → full life + armor
--   /tp <x> <y> <z>     → teleporte
--   /tpm                → teleporta pra onde você marcou no mapa (waypoint)

RegisterCommand('car', function(_, args)
    local model = args[1] or 'adder'
    local hash = GetHashKey(model)
    if not IsModelInCdimage(hash) or not IsModelAVehicle(hash) then
        TriggerEvent('chat:addMessage', { args = { '[dev]', 'model inválido: ' .. model } })
        return
    end
    RequestModel(hash)
    local t = 0
    while not HasModelLoaded(hash) and t < 200 do Wait(10); t = t + 1 end
    if not HasModelLoaded(hash) then
        TriggerEvent('chat:addMessage', { args = { '[dev]', 'falha ao carregar model ' .. model } })
        return
    end
    local ped = PlayerPedId()
    local pos = GetEntityCoords(ped)
    local heading = GetEntityHeading(ped)
    local veh = CreateVehicle(hash, pos.x + 2.0, pos.y, pos.z, heading, true, false)
    SetEntityAsMissionEntity(veh, true, true)
    SetVehicleHasBeenOwnedByPlayer(veh, true)
    SetVehicleNeedsToBeHotwired(veh, false)
    SetModelAsNoLongerNeeded(hash)
    TriggerEvent('chat:addMessage', { args = { '[dev]', 'spawned ' .. model } })
end, false)

RegisterCommand('dv', function()
    local ped = PlayerPedId()
    local veh = GetVehiclePedIsIn(ped, false)
    if veh ~= 0 then
        SetEntityAsMissionEntity(veh, true, true)
        DeleteVehicle(veh)
        return
    end
    -- se não tá em carro, apaga o mais próximo
    local pos = GetEntityCoords(ped)
    for _, v in ipairs(GetGamePool('CVehicle')) do
        if #(GetEntityCoords(v) - pos) < 5.0 then
            SetEntityAsMissionEntity(v, true, true)
            DeleteVehicle(v)
            return
        end
    end
end, false)

RegisterCommand('weapon', function(_, args)
    local w = args[1] or 'weapon_pistol'
    local ammo = tonumber(args[2] or 250)
    GiveWeaponToPed(PlayerPedId(), GetHashKey(w), ammo, false, true)
    TriggerEvent('chat:addMessage', { args = { '[dev]', ('arma %s (x%d)'):format(w, ammo) } })
end, false)

RegisterCommand('heal', function()
    local ped = PlayerPedId()
    SetEntityHealth(ped, GetEntityMaxHealth(ped))
    SetPedArmour(ped, 100)
end, false)

RegisterCommand('tp', function(_, args)
    local x = tonumber(args[1]); local y = tonumber(args[2]); local z = tonumber(args[3])
    if not (x and y and z) then
        TriggerEvent('chat:addMessage', { args = { '[dev]', 'uso: /tp <x> <y> <z>' } })
        return
    end
    SetEntityCoords(PlayerPedId(), x + 0.0, y + 0.0, z + 0.0, false, false, false, true)
end, false)

RegisterCommand('tpm', function()
    local wp = GetFirstBlipInfoId(8)  -- waypoint
    if not DoesBlipExist(wp) then
        TriggerEvent('chat:addMessage', { args = { '[dev]', 'marca um ponto no mapa primeiro' } })
        return
    end
    local coords = GetBlipInfoIdCoord(wp)
    local ped = PlayerPedId()
    -- Pega z válido no chão
    local z = coords.z
    for i = 0, 1000 do
        local ok, groundZ = GetGroundZFor_3dCoord(coords.x, coords.y, i + 0.0, false)
        if ok then z = groundZ; break end
        Wait(0)
    end
    SetEntityCoords(ped, coords.x, coords.y, z, false, false, false, true)
end, false)

print('[dev_commands] carregado. /car /dv /weapon /heal /tp /tpm')
