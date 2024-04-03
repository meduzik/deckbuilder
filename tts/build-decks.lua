local net_data = nil
local deck_path = "example/deck.xml"

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
		
		local deck_width = 3.2 * deck.scale
		local deck_height = 3.2 * deck.scale
		local padding = 0.4
		local spread_elevation = 5
		local spread_layer_height = 0.5
		
		if deck.width > deck.height then
			deck_height = deck_height * (deck.height / deck.width)
		else
			deck_width = deck_width * (deck.width / deck.height)
		end
		
		pos.x = pos.x + deck_width * 0.5
		
		local pos_deck = {x=pos.x, y=pos.y + spread_elevation, z=pos.z + padding + deck_height * 0.5}
		local pos_spread = {x=pos.x + padding + deck_width, y=pos.y + spread_elevation, z=pos.z + padding + deck_height * 0.5}
		local off_spread = {x=padding + deck_width, y=spread_layer_height, z=padding + deck_height}
		
		local rows = 10
		local cols = 10
		local order = 0
		
		local card_library = {}
		
		-- load and spread sheets
		for sheet_idx, sheet in ipairs(deck.sheets) do
			print("Spawning sheet ", sheet_idx)
			local sheet_deck = spawnObject({
				type = "DeckCustom",
				position = {x=pos_deck.x, y=pos_deck.y, z=pos_deck.z},
				scale = {deck.scale, deck.scale, deck.scale}
			})
			local data = {
				face = sheet.face,
				back = sheet.back,
				width = sheet.width,
				height = sheet.height,
				number = sheet.count,
				back_is_hidden = not sheet.has_face_hidden,
				unique_back = sheet.unique_backs
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
					position = {
						x = pos_spread.x + off_spread.x * col,
						y = pos_spread.y + off_spread.y * layer,
						z = pos_spread.z + off_spread.z * row
					},
					smooth = false
				}
				if sheet.unique_backs then
					card.hide_when_face_down = false
				end
				card.setLock(true)
				if card_info.name then
					card.setName(card_info.name)
				end
				if card_info.description then
					card.setDescription(card_info.description)
				end
				card_library[card_info.index] = card
				order = order + 1
			end
			wait_frames(10)
		end
		
		print("Building stack")		
		local stack_offset = 0.2
		local stack_elev = 1.75
		local next_card_idx = 1
		
		local stack_deck = nil
		
		local function spawn_next_card(spawn_pos)
			if next_card_idx > #deck.stack then
				return nil
			end
			local card_idx = deck.stack[#deck.stack - next_card_idx + 1]
			local card_clone = card_library[card_idx].clone {
				position = spawn_pos,
				snap_to_grid = false
			}
			card_clone.setPosition(spawn_pos)
			card_clone.setRotation({0, 180, 0})
			card_clone.setLock(true)
			next_card_idx = next_card_idx + 1
			return card_clone
		end
	
		local stack_pos = {
			x = pos.x,
			y = pos.y + stack_elev,
			z = pos.z - deck_height * 0.5
		}
		
		-- place the first card where the deck should be
		local card1 = spawn_next_card(stack_pos)
		
		local spawn_pos = {
			x = stack_pos.x,
			y = stack_pos.y + stack_offset,
			z = stack_pos.z
		}
		
		-- then place the second card above it
		-- and force them to stack
		local card2 = spawn_next_card(spawn_pos)
		
		if card1 and card2 then
			-- let some time for cards and deck to settle
			coroutine.yield(0)
			card1.setLock(false)
			card2.setLock(false)
			card1.putObject(card2)
			coroutine.yield(0)
			-- find the newly creted deck object
			stack_deck = find_the_deck(stack_pos)
			stack_deck.setLock(true)
		elseif card1 then
			stack_deck = card1
		end
		
		local has_more = true
		local chunk_idx = 1
		while has_more do
			local extra_cards = {}
			spawn_pos.y = stack_pos.y + stack_offset * (1 + 10 * chunk_idx)
			for i = 1, 100 do
				spawn_pos.y = spawn_pos.y + stack_offset
				local card = spawn_next_card(spawn_pos)
				if not card then
					has_more = false
					break
				end
				table.insert(extra_cards, card)
			end
			wait_frames(10)		
			for _, card in ipairs(extra_cards) do
				stack_deck.setLock(false)
				card.setLock(false)
				stack_deck:putObject(card, {smooth=false})
				stack_deck.setLock(true)
			end
			wait_frames(10)
			if has_more then
				wait_frames(20)
			end
			chunk_idx = chunk_idx + 1
		end
		if stack_deck then 
			stack_deck:setLock(false)
		end
		
		print("Destroying library")
		for _, card_object in pairs(card_library) do
			card_object.destruct()
		end
		wait_frames(10)
		
		pos.x = pos.x + deck_width * 0.5 + padding
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

function find_the_deck(pos)
	local hit_list = find_hits_in_radius(pos, 4)
	local closest = nil
	for _, hit in ipairs(hit_list) do
		if hit.hit_object.tag == "Deck" then
			if (not closest) or (closest.distance > hit.distance) then
				closest = hit
			end
		end
	end
	if not closest then
		error("cannot find the deck! something went wrong")
	end
	local deck = closest.hit_object
	return deck
end

function find_hits_in_radius(pos, radius)
    local hit_list = Physics.cast({
        origin       = pos,
		direction    = {0,1,0},
        type         = 2,
        size         = {radius,radius,radius},
        max_distance = 0,
        debug        = true,
    })
    return hit_list
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


