-- ==========================================================================
-- SERVER — recebe HTTP do cérebro Python e repassa pro client.
-- Um único endpoint: POST /acessibilidade_gta/command  body: { action, ...params }
-- ==========================================================================

local function getMasterSource()
    local players = GetPlayers()
    return players[1]  -- pro caso de 1 jogador na instância (dev). Servers reais precisam lógica de owner.
end

SetHttpHandler(function(req, res)
    local path = req.path or ''
    local ok = (path == '/command' or path == '/acessibilidade_gta/command')
               and req.method == 'POST'
    if not ok then
        res.writeHead(404); res.send('not found'); return
    end
    req.setDataHandler(function(body)
        local ok, data = pcall(json.decode, body)
        if not ok or not data or not data.action then
            res.writeHead(400); res.send('bad json'); return
        end
        local master = getMasterSource()
        if not master then
            res.writeHead(503); res.send('no player online'); return
        end
        TriggerClientEvent('acessibilidade_gta:command', tonumber(master), data)
        res.writeHead(200); res.send('ok')
    end)
end)

print('[acessibilidade_gta] HTTP handler em /acessibilidade_gta/command')

-- Hooks opcionais usados quando Config.Framework = 'custom': o admin pode
-- registrar listeners pra esses eventos e rodar o código do server dele.
-- (Mantém o resource agnóstico — não importamos QBCore/ESX diretamente.)
