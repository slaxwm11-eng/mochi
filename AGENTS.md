# AGENTS.md

This document describes the agents, tools, and core components available in the `mochi.py` codebase. It serves as a reference for understanding the bot's capabilities, internal APIs, and interaction flows.

## 🤖 Main Agent: MashuBot
**Description:** The central controller of the chatbot. It simulates a 23-year-old game-addicted, slightly cynical employee living in Japan.
**Core Responsibilities:**
- Receives Webhook payloads from NapCat (QQ bot framework).
- Classifies user intents via an LLM.
- Dispatches tasks to specific sub-modules/tools based on the intent.
- Manages the personality prompt and conversation context.
- Coordinates the asynchronous TTS (Text-to-Speech) delivery.

---

## 🛠 Tools & Sub-Agents

### 1. Intelligent Memory Engine (`IntelligentMemoryEngine`)
**Description:** A background tool that consolidates user chat history into structured, long-term psychological profiles and relationship dynamics.
- **Input:** `user_id` (int), `user_name` (str), `interaction_log` (str).
- **Processing:** Uses an LLM to analyze the recent dialogue and merge it with existing JSON-based memory profiles. It strictly filters out gaming noise (like KDA) and focuses on traits and habits.
- **Output:** Saves a structured JSON file (`intelligent_memory.json`).
- **Interaction:** Run asynchronously via a queue (`consolidation_queue`) to avoid blocking the main chat loop.

### 2. Dota API Tool (`DotaAPI`)
**Description:** A wrapper for fetching live and historical Dota 2 data using the Stratz GraphQL API.
- **Functions:**
  - `get_match_single(steam_id)`: Fetches the most recent match for a given player, returning KDA, GPM, and MVP status.
  - `get_match_recent(steam_id)`: Aggregates the last 10 matches, calculating win rates and top heroes.
  - `get_hero_stats(hero_name_hint)`: Fetches win rates and popular item builds for a specific hero.
  - `get_top_heroes()`: Retrieves the top 10 heroes with the highest win rates in the Ancient+ brackets.
- **Input:** Steam ID or Hero Name.
- **Output:** Parsed JSON dictionaries containing relevant game statistics.

### 3. Live Camera Tool (`_handle_live_camera`)
**Description:** Fetches real-time snapshots from global webcams via the Windy API based on city names, countries, or coordinates.
- **Input:** `scene_type` (e.g., "work", "off_work", "trip", "city_view"), and optionally a `city` name.
- **Processing:** Resolves the city to a country code or coordinates via an LLM, queries the Windy API for active webcams within a radius, and randomly selects one to download.
- **Output:** Sends an image file to the chat along with an LLM-generated, character-consistent commentary.

### 4. NASA Space Image Tool (`_handle_nasa_space`)
**Description:** Retrieves the NASA Astronomy Picture of the Day (APOD).
- **Input:** An optional date string (YYYY-MM-DD). If no date is provided, it may randomly select a historical date.
- **Output:** Sends the high-definition space image to the chat, accompanied by an LLM-generated translation/commentary of the astronomical description.

### 5. Animal Camera Tool (`AnimalLiveCamera` / `_animal_worker`)
**Description:** Hooks into an external module (`animal_cam.py`) to provide live or cached feeds of specific animals or nature scenes.
- **Input:** A keyword from the user's message (e.g., "猫", "狗", "老鹰").
- **Processing:** Uses exact matching or LLM-based entity extraction to find the target animal in the predefined map.
- **Output:** Sends a GIF/image from the requested camera feed.

### 6. Voice / TTS Engine (`_voice_worker` & `clean_bot_text`)
**Description:** Converts the bot's text responses into voice messages using Microsoft Edge TTS.
- **Input:** Raw text response from the LLM.
- **Processing:** 1. `clean_bot_text`: Pre-processes the text by removing markdown, expanding Dota slang (e.g., "KDA" -> "K D A"), and tweaking punctuation to force specific emotional tones (e.g., substituting "?" with "？？" to raise pitch).
  2. Generates an MP3 file asynchronously.
- **Output:** Sends a voice record message (`[CQ:record,...]`) to the NapCat framework.

---

## 📡 API Interactions & Conventions
- **LLM Provider:** DeepSeek (configured via `OpenAI` client). Uses `deepseek-v4-pro` for complex tasks (like flaming a player's stats) and `deepseek-v4-flash` for quick intent classification.
- **Message Sending:** HTTP POST requests to NapCat (`Config.NAPCAT_URL`/send_group_msg).
- **Concurrency:** Uses `threading` extensively to handle memory updates, audio generation, and the proactive scheduled task (`_auto_speak_loop`) without freezing the main Flask webhook receiver.
