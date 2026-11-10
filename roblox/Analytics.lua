--!strict
-- Analytics: batches gameplay events and sends them to the analytics API.
-- Disabled (no-op) until API_URL below is set, so it is safe to leave connected.
-- Setup: Game Settings > Security > enable "Allow HTTP Requests", and store the API key
-- in Studio's Secrets (name: analytics_api_key) so it never appears in source.
--
-- Usage (server only):
--   Analytics.track(player, "steal", { zone = 3, amount = crateWeight })

local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local API_URL = "https://YOUR-API-HOST/v1/events" -- set after deploying
local FLUSH_INTERVAL = 10 -- seconds
local MAX_BATCH = 100     -- API limit; HttpService allows ~500 requests/min per server
local MAX_QUEUE = 1000    -- drop oldest events instead of growing without bound

local Analytics = {}

local queue: { { [string]: any } } = {}
local sessionIds: { [number]: string } = {}
local enabled = API_URL:find("YOUR%-API%-HOST") == nil

type Fields = { zone: number?, rarity: string?, amount: number?, data: { [string]: any }? }

function Analytics.track(player: Player, eventType: string, fields: Fields?)
	if not enabled then return end
	local ok = pcall(function()
		local f = fields or {}
		if #queue >= MAX_QUEUE then
			table.remove(queue, 1)
		end
		table.insert(queue, {
			type = eventType,
			user_id = player.UserId,
			ts = os.time(),
			session_id = sessionIds[player.UserId],
			zone = f.zone,
			rarity = f.rarity,
			amount = f.amount,
			data = f.data or {},
		})
	end)
	if not ok then warn("[Analytics] track failed") end
end

local function flush()
	if #queue == 0 then return end
	local batch = {}
	for _ = 1, math.min(#queue, MAX_BATCH) do
		table.insert(batch, table.remove(queue, 1))
	end
	local ok, res = pcall(function()
		return HttpService:RequestAsync({
			Url = API_URL,
			Method = "POST",
			Headers = {
				["Content-Type"] = "application/json",
				["X-API-Key"] = HttpService:GetSecret("analytics_api_key") :: any,
			},
			Body = HttpService:JSONEncode({ events = batch }),
		})
	end)
	if not ok or not res.Success then
		-- Analytics must never hurt gameplay: put the batch back (bounded) and retry next tick.
		for i = #batch, 1, -1 do
			if #queue < MAX_QUEUE then table.insert(queue, 1, batch[i]) end
		end
		warn("[Analytics] flush failed:", ok and res.StatusCode or res)
	end
end

local function onJoin(player: Player)
	sessionIds[player.UserId] = HttpService:GenerateGUID(false)
	Analytics.track(player, "session_start")
end

Players.PlayerAdded:Connect(onJoin)
for _, p in ipairs(Players:GetPlayers()) do
	onJoin(p)
end

Players.PlayerRemoving:Connect(function(player)
	Analytics.track(player, "session_end")
	local uid = player.UserId
	task.delay(FLUSH_INTERVAL * 2, function() sessionIds[uid] = nil end)
end)

if enabled then
	task.spawn(function()
		while true do
			task.wait(FLUSH_INTERVAL)
			flush()
		end
	end)

	game:BindToClose(function()
		if RunService:IsStudio() then return end
		flush()
	end)
end

return Analytics
