local net_data = nil
local deck_path = nil

function on_input(obj, color, input)
	deck_path = input
end

function load_and_build()
	print("QUERYING FOR DECKS...")
	
	local function build_decks(response)
		print("GOT RESPONSE")
		
		net_data = response.text

		startLuaCoroutine(self, "build_decks")
	end
	
	WebRequest.get("http://localhost:17352/?deck=" .. deck_path, build_decks)
end

function build_decks()
	local data = JSON.decode(net_data)
	if data.error then
		print("Server error: ", data.error)
		return 0
	end
	
	local decks = data.response.decks
	
	print("Building decks")
	
	local pos = self.getPosition()
	
	pos.x = pos.x + 2
	
	for _, deck in ipairs(decks) do
		print("Building deck ", deck.name)
		
		pos.x = pos.x + 3 * deck.scale
		
		local pos_spread = {x=pos.x, y=pos.y + 5, z=pos.z + 3.1}
		local off_spread = {x=3.1, y=1, z=3.1}
		
		local rows = 10
		local cols = 10
		local order = 0
		
		local card_library = {}
		
		-- load and spread sheets
		for sheet_idx, sheet in ipairs(deck.sheets) do
			print("Spawning sheet ", sheet_idx)
			local sheet_deck = spawnObject({
				type = "DeckCustom",
				position = {x=pos.x + sheet_idx * (3 * deck.scale + 0.1), y=pos.y + 1, z=pos.z}
			})
			local data = {
				face = sheet.face,
				back = sheet.back,
				width = sheet.width,
				height = sheet.height,
				number = sheet.count,
				back_is_hidden = not sheet.has_face_hidden,
				unique_backs = sheet.unique_backs
			}
			sheet_deck.setCustomObject(data)
			sheet_deck.setLock(true)
			wait_frames(10)
			print("Spreading sheet")
			for card_idx, card_info in irpairs(sheet.cards) do
				local col = order % cols
				local row = math.floor(order / cols) % rows
				local layer = math.floor(order / (cols * rows))
				local card = sheet_deck.takeObject {
					position = {x = pos_spread.x + off_spread.x * col, y = pos_spread.y + off_spread.y * layer, z = pos_spread.z + off_spread.z * row},
					smooth = false
				}
				card.setLock(true)
				if card_info.name then
					card.setName(card_info.name)
				end
				if card_info.description then
					card.setDescription(card_info.description)
				end
				card_library[card_info.index] = card
				order = order + 1
				coroutine.yield(0)
			end
			wait_frames(10)
		end
		
		print("Building stack")
		
		local stack_cards = {}
		local stack_offset = 0.2
		local stack_elev = 1.75
		
		local spawn_pos = {x=pos.x, y=pos.y + stack_elev + stack_offset * #deck.stack, z=pos.z}
		
		for idx, card_idx in ipairs(deck.stack) do
			local card_clone = card_library[card_idx].clone {
				position = spawn_pos,
				snap_to_grid = false
			}
			card_clone.setPosition(spawn_pos)
			card_clone.setRotation({0, 180, 0})
			card_clone.setScale({deck.scale, deck.scale, deck.scale})
			spawn_pos.y = spawn_pos.y - stack_offset
			card_clone.setLock(true)
			table.insert(stack_cards, card_clone)
		end
		
		wait_frames(10)
		
		for idx = #stack_cards, 1, -1 do
			local card_object = stack_cards[idx]
			card_object.setLock(false)
			coroutine.yield(0)
		end
		
		wait_frames(10)
		print("Destroying library")
		for _, card_object in pairs(card_library) do
			card_object.destruct()
			coroutine.yield(0)
		end
		wait_frames(10)
	end
	
	print("Building decks DONE!")
	
	return 1
end

function wait_frames(frames)
    for _ = 1, frames do
		coroutine.yield(0)
	end
end


local function reversedipairsiter(t, i)
    i = i - 1
    if i ~= 0 then
        return i, t[i]
    end
end

function irpairs(t)
    return reversedipairsiter, t, #t + 1
end

function onLoad()
    self.createButton({
        click_function="load_and_build",
		function_owner=self,
        position={0,0.2,-0.6},
		height=600,
		width=640,
		color={1,1,1,0},
		label="BUILD!",
        tooltip="Click to build"
    })
	self.createInput({
		input_function="on_input",
		function_owner = self,
        label = "Deck path",
		alignment = 2,
		scale = {0.4, 0.4, 0.4},
        position = {x=0, y=0.2, z=0.8},
        width = 2000,
        height = 200,
        font_size = 120
	})
end

