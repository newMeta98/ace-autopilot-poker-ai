import json
import keyboard
from PIL import Image
import moondream as md
import mss
import pytesseract
import os
import re
import sys
import cv2
import numpy as np
from datetime import datetime
from collections import defaultdict
import tkinter as tk
from threading import Thread
from utils.api_client import poker_ai_decision
import pyautogui
import time

# Initialize vision model
model = md.vl(model="X:/projects/poker_master/moondream-2b-int8.mf")

# Coordinates configuration
COORDINATES = {
    # Player cards
    "your_card1": {"top": 610, "left": 374, "width": 38, "height": 48},
    "your_card2": {"top": 585, "left": 470, "width": 37, "height": 47},
    # Community cards
    "table_card1": {"top": 423, "left": 213, "width": 28, "height": 47},
    "table_card2": {"top": 423, "left": 320, "width": 28, "height": 47},
    "table_card3": {"top": 423, "left": 427, "width": 28, "height": 47},
    "table_card4": {"top": 423, "left": 533, "width": 28, "height": 47},
    "table_card5": {"top": 423, "left": 640, "width": 28, "height": 47},
    # Interface elements
    "you_actions_symbol": {"top": 790, "left": 403, "width": 132, "height": 30},
    "player1_actions": {"top": 716, "left": 73, "width": 105, "height": 26},
    "player2_actions": {"top": 472, "left": 33, "width": 105, "height": 26},
    "player3_actions": {"top": 472, "left": 802, "width": 105, "height": 26},
    "player4_actions": {"top": 716, "left": 758, "width": 105, "height": 26},
    "your_balance": {"top": 716, "left": 403, "width": 135, "height": 26},
    "pot": {"top": 335, "left": 350, "width": 240, "height": 70},
    # Fold detection regions
    "player1_fold": {"top": 600, "left": 70, "width": 110, "height": 60},
    "player2_fold": {"top": 355, "left": 28, "width": 110, "height": 60},
    "player3_fold": {"top": 355, "left": 800, "width": 110, "height": 60},
    "player4_fold": {"top": 600, "left": 756, "width": 110, "height": 60},
    # Action buttons (Dummy coordinates - replace with your actual values)
    "fold_button": {"top": 875, "left": 214, "width": 105, "height": 34},
    "call_button": {"top": 875, "left": 420, "width": 105, "height": 34},
    "raise_button": {"top": 875, "left": 620, "width": 105, "height": 34},
    "check_button": {"top": 875, "left": 420, "width": 105, "height": 34},
    "raise_confirm": {"top": 878, "left": 889, "width": 36, "height": 36},
    "ai_turn": {"top": 866, "left": 192, "width": 151, "height": 51},  # Your action box
    "round_end": {"top": 903, "left": 305, "width": 336, "height": 31},  # Pot area when empty
    "new_hand": {"top": 866, "left": 192, "width": 151, "height": 51},  # First card position
    "flop_cards": {"top": 544, "left": 261, "width": 91, "height": 17},
    "turn_card": {"top": 544, "left": 526, "width": 106, "height": 18},
    "river_card": {"top": 543, "left": 633, "width": 104, "height": 16},
}

# Add template images paths
TEMPLATES = {
    "ai_turn": cv2.imread("symbol_templates/your_turn.png", cv2.IMREAD_GRAYSCALE),
    "round_end": cv2.imread("symbol_templates/empty_pot.png", cv2.IMREAD_GRAYSCALE),
    "new_hand": cv2.imread("symbol_templates/card_back.png", cv2.IMREAD_GRAYSCALE),
    "flop_cards": cv2.imread("symbol_templates/flop_cards.png", cv2.IMREAD_GRAYSCALE),
    "turn_card": cv2.imread("symbol_templates/turn_card.png", cv2.IMREAD_GRAYSCALE),
    "river_card": cv2.imread("symbol_templates/river_card.png", cv2.IMREAD_GRAYSCALE)
}

# Simplified button coordinates
BUTTON_COORDINATES = {
    "fold": (
        COORDINATES["fold_button"]["left"] + COORDINATES["fold_button"]["width"]//2,
        COORDINATES["fold_button"]["top"] + COORDINATES["fold_button"]["height"]//2
    ),
    "call": (
        COORDINATES["call_button"]["left"] + COORDINATES["call_button"]["width"]//2,
        COORDINATES["call_button"]["top"] + COORDINATES["call_button"]["height"]//2
    ),
    "check": (
        COORDINATES["check_button"]["left"] + COORDINATES["check_button"]["width"]//2,
        COORDINATES["check_button"]["top"] + COORDINATES["check_button"]["height"]//2
    ),
    "raise": [
        (
            COORDINATES["raise_button"]["left"] + COORDINATES["raise_button"]["width"]//2,
            COORDINATES["raise_button"]["top"] + COORDINATES["raise_button"]["height"]//2
        ),
        (
            COORDINATES["raise_confirm"]["left"] + COORDINATES["raise_confirm"]["width"]//2,
            COORDINATES["raise_confirm"]["top"] + COORDINATES["raise_confirm"]["height"]//2
        )
    ]
}

# Global state
formatted_data = defaultdict(dict)
captured_cards = set()
current_phase = 1
ai_folded = False
round_active = False
automation_enabled = False

PHASE_CONFIG = {
    1: {
        "name": "New Hand/Pre-Flop",
        "expected_actions": 1,
        "cards": ["your_card1", "your_card2"],
        "always_capture": [
            "your_balance", "pot", "you_actions_symbol",
            "player1_actions", "player2_actions",
            "player3_actions", "player4_actions"
        ],
        "table_cards": []
    },
    2: {
        "name": "Post-Flop",
        "expected_actions": 2,
        "cards": ["table_card1", "table_card2", "table_card3"],
        "always_capture": [
            "your_balance", "pot", "you_actions_symbol",
            "player1_actions", "player2_actions",
            "player3_actions", "player4_actions"
        ],
        "table_cards": ["table_card1", "table_card2", "table_card3"]
    },
    3: {
        "name": "Post-Turn",
        "expected_actions": 3,
        "cards": ["table_card4"],
        "always_capture": [
            "your_balance", "pot", "you_actions_symbol",
            "player1_actions", "player2_actions",
            "player3_actions", "player4_actions"
        ],
        "table_cards": ["table_card4"]
    },
    4: {
        "name": "Post-River",
        "expected_actions": 4,
        "cards": ["table_card5"],
        "always_capture": [
            "your_balance", "pot", "you_actions_symbol",
            "player1_actions", "player2_actions",
            "player3_actions", "player4_actions"
        ],
        "table_cards": ["table_card5"]
    }
}

# Fold template image
FOLD_TEMPLATE = cv2.imread("symbol_templates/fold.png", cv2.IMREAD_GRAYSCALE)

# Overlay window for logs
class OverlayWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Calculate window dimensions (98% height, right-aligned)
        window_width = 300
        window_height = int(screen_height * 0.73)
        x_position = screen_width - window_width - 17  # 17px from right edge
        y_position = 215  # 35px from top
        
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        self.root.attributes("-topmost", True)
        # self.root.attributes("-alpha", 0.9)   Optional: slight transparency
        self.root.configure(bg="black")
        
        # Configure text widget
        self.log_text = tk.Text(
            self.root, 
            bg="black", 
            fg="white", 
            wrap=tk.WORD,
            font=("Consolas", 10)  # Better for logs
        )
        self.log_text.pack(expand=True, fill=tk.BOTH)
        
        # Add scrollbar
        scrollbar = tk.Scrollbar(self.root, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def update_log(self, message):
        self.root.after(0, self._update_log, message)
    
    def _update_log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        
        # Convert line number to integer before comparison
        current_line = int(self.log_text.index(tk.END).split('.')[0])
        if current_line > 1000:
            self.log_text.delete(1.0, 2.0)

    def run(self):
        self.root.mainloop()

overlay = OverlayWindow()

# Add this function to handle AI actions
def perform_ai_action(decision):
    global ai_folded
    """Execute the AI's decision through mouse clicks"""
    action = decision["final_decision"].lower()
    overlay.update_log(f"🖱️ Attempting to perform action: {action.upper()}")
    
    action_mapping = {
        "fold": [BUTTON_COORDINATES["fold"]],
        "call": [BUTTON_COORDINATES["call"]],
        "check": [BUTTON_COORDINATES["check"]],
        "raise": BUTTON_COORDINATES["raise"]
    }
    
    if action not in action_mapping:
        overlay.update_log(f"❌ Unknown action: {action}")
        return
    
    coordinates = action_mapping[action]
    
    try:
        for step, (x, y) in enumerate(coordinates, 1):
            pyautogui.moveTo(x, y, duration=0.25 + np.random.uniform(0, 0.1))
            time.sleep(0.15 + np.random.uniform(0, 0.05))
            pyautogui.click()
            overlay.update_log(f"✅ Step {step}: Clicked {action.upper()} at ({x}, {y})")
            time.sleep(0.2 + np.random.uniform(0, 0.1))
        
        # Update action history
        action_text = action.capitalize()
        if action == "raise" and "amount" in decision:
            action_text += f" {decision['amount']}"
        
        formatted_data["player_actions"]["You"]["history"].append({
            "phase": formatted_data["game_phase"],
            "action": action_text,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })
        
    except Exception as e:
        overlay.update_log(f"❌ Failed to perform action: {str(e)}")

    if action == "fold":
        ai_folded = True

def initialize_environment():
    """Set up required directories and resources"""
    if not os.path.exists("screenshots"):
        os.makedirs("screenshots")
    overlay.update_log("🖥️ Poker Analyst Initialized")
    overlay.update_log("⏳ Press ESC to quit the program")
    overlay.update_log("⌨️ Press Alt+A - Toggle automation")
    overlay.update_log("⏳ Waiting for game input...")

def capture_screenshot(region, key):
    """Capture and save screenshot of specific region"""
    overlay.update_log(f"  📸 Capturing {key} region...")
    with mss.mss() as sct:
        monitor = {k: v for k, v in region.items()}
        screenshot = sct.grab(monitor)
        image = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        filename = f"screenshots/{key}.png"
        image.save(filename)
        overlay.update_log(f"  ✅ Screenshot saved to {filename}")
        return image

def process_card(image, key):
    """Process card image using vision model"""
    overlay.update_log(f"  🃏 Processing {key}...")
    
    # Rotate the image if it's a tilted card
    if "your_card" in key:
        angle = -21 if "your_card1" in key else 23
        image = rotate_image(image, angle)
        overlay.update_log(f"  🔄 Rotated {key} by {angle}°")

    encoded_image = model.encode_image(image)
    
    # Get card details
    overlay.update_log(f"  🔍 Identifying {key} symbol...")
    symbol_response = model.query(encoded_image, "What symbol is shown on the card?")["answer"]
    
    overlay.update_log(f"  🔍 Identifying {key} value...")
    value_response = model.query(encoded_image, "What number/letter is shown on the card?")["answer"]
    
    return {
        "symbol": clean_symbol(symbol_response),
        "value": clean_value(value_response),
        "key": key
    }

def clean_symbol(symbol):
    """Normalize card symbols"""
    symbol = symbol.lower().strip()
    suits = {
        "spade": "Spades",
        "heart": "Hearts",
        "diamond": "Diamonds",
        "club": "Clubs"
    }
    for k, v in suits.items():
        if k in symbol:
            return v
    overlay.update_log(f"⚠️ Unknown card symbol detected: {symbol}")
    return "Unknown"

def clean_value(value):
    """Validate and normalize card values"""
    value = value.strip().upper()
    pattern = r'\b(A|2|3|4|5|6|7|8|9|10|J|Q|K)\b'
    match = re.search(pattern, value)
    if not match:
        overlay.update_log(f"⚠️ Unrecognized card value: {value}")
        return None
    return match.group()

def process_interface_field(image, key):
    """Process non-card game elements with phase awareness"""
    text = pytesseract.image_to_string(image, lang='eng', config='--psm 6').strip()
    
    if "actions" in key:
        player_key = key.split("_")[0].capitalize()
        if player_key.lower() == "you":
            player_key = "You"
            
        player_actions = formatted_data["player_actions"].get(player_key, {"current": "", "history": []})
        current_history = player_actions.get("history", [])
        
        # Clean and normalize action
        text = text.strip() or "no action"
        action = normalize_action(text)
        
        if not action:
            return ""

        # Get current phase information
        global current_phase
        phase_key = f"Phase {current_phase}"
        
        # Check for existing entry in this phase
        existing_entry = next(
            (entry for entry in current_history 
             if entry.get("phase") == phase_key),
            None
        )
        
        if existing_entry:
            # Update existing action if different
            if existing_entry["action"] != action:
                existing_entry["action"] = action
                existing_entry["timestamp"] = datetime.now().strftime("%H:%M:%S")
                overlay.update_log(f"  🔄 Updated {player_key} action to {action}")
        else:
            # Add new entry for this phase
            new_entry = {
                "phase": phase_key,
                "action": action,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
            current_history.append(new_entry)
            overlay.update_log(f"  📝 Added {player_key} action: {action}")

        # Update current action reference
        player_actions["current"] = action
        formatted_data["player_actions"][player_key] = player_actions
        
        return action
        
    # Handle other field types
    else:
        return str(text)

# In detect_fold(), add debug logging:
def detect_fold(image, player):
    overlay.update_log(f"  👀 Checking fold status for {player}...")
    screenshot_gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    
    # NEW: Save match visualization
    result = cv2.matchTemplate(screenshot_gray, FOLD_TEMPLATE, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    
    # Debug logging
    overlay.update_log(f"  🔍 Fold match value: {max_val:.2f}")
    if max_val > 0.4:
        # NEW: Save detection snapshot
        h, w = FOLD_TEMPLATE.shape
        top_left = max_loc
        bottom_right = (top_left[0] + w, top_left[1] + h)
        cv2.rectangle(screenshot_gray, top_left, bottom_right, 255, 2)

    return max_val > 0.4

def handle_phase(phase):
    global current_phase
    if phase == 1:
        reset_game_state()
    elif phase != current_phase:
        overlay.update_log(f"⚠️ Phase jump detected! Current: {current_phase}, Received: {phase}")
        return

    formatted_data["game_phase"] = PHASE_CONFIG[phase]["name"]

    update_game_state()
    overlay.update_log(f"\n🎚️ PHASE {phase} TRIGGERED")
    process_phase_data(phase)
    
    # Only increment phase if in normal flow
    if phase == current_phase:
        current_phase += 1 if phase < 4 else 0
        
    overlay.update_log(f"✅ Phase {phase} completed\n")


    save_game_state()
    display_current_state()
    overlay.update_log("✅ Game state update complete")

    # New: Auto-trigger AI analysis
    ai_decision = get_ai_decision()
    if ai_decision:
        overlay.update_log(f"🤖 AI Recommendation: {ai_decision['final_decision'].upper()}")
        overlay.update_log(f"💡 Reasoning: {ai_decision['thinking_process']}")
        perform_ai_action(ai_decision)
        return ai_decision

def infer_missing_actions():
    global formatted_data, current_phase
    
    if current_phase == 1:
        return

    previous_phase = current_phase - 1
    overlay.update_log(f"\n🔍 Inferring Phase {previous_phase} missing actions")
    
    # Check for raises in previous phase
    raise_in_prev = any(
        any("Raise" in entry.get("action", "") or "Bet" in entry.get("action", "")
            for entry in player_data["history"]
            if entry.get("phase") == f"Phase {previous_phase}")
        for player_data in formatted_data["player_actions"].values()
    )

    # Infer missing previous phase actions
    for player in ["Player1", "Player2", "Player3", "Player4", "You"]:
        player_data = formatted_data["player_actions"].setdefault(
            player, {"current": "", "history": []}
        )
        history = player_data["history"]
        
        # Skip folded players
        if any(entry.get("action") == "Fold" for entry in history):
            continue
            
        # Check if has previous phase action
        has_prev_action = any(
            entry.get("phase") == f"Phase {previous_phase}"
            for entry in history
        )

        if not has_prev_action:
            action = "Call" if raise_in_prev else "Check"
            history.append({
                "phase": f"Phase {previous_phase}",
                "action": action,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })
            overlay.update_log(f"  ⚙️ Inferred {player} Phase {previous_phase}: {action}")

def update_current_action_status():
    """Update current action status without modifying history"""
    global formatted_data, current_phase
    overlay.update_log("\n🔄 Updating current action status")
    
    for player in ["Player1", "Player2", "Player3", "Player4", "You"]:
        player_data = formatted_data["player_actions"].setdefault(
            player, {"current": "", "history": []}
        )
        
        # Preserve existing current action if set
        if player_data["current"]:
            continue
            
        # Check folding status
        is_folded = any(entry.get("action") == "Fold" for entry in player_data["history"])
        
        # Check if has current phase action
        has_current_action = any(
            entry.get("phase") == f"Phase {current_phase}"
            for entry in player_data["history"]
        )

        if is_folded:
            player_data["current"] = "Fold"
        elif not has_current_action:
            player_data["current"] = "not played yet"
            overlay.update_log(f"  ⏳ {player} marked as 'not played yet'")


def process_phase_data(phase):
    """Process data for specific game phase"""
    global formatted_data
    
    config = PHASE_CONFIG[phase]
    overlay.update_log(f"📦 Processing phase configuration...")
    

    # Process new cards
    overlay.update_log(f"🖼️ Capturing {len(config['cards'])} card(s)")
    for card_key in config["cards"]:
        if card_key not in captured_cards:
            image = capture_screenshot(COORDINATES[card_key], card_key)
            card_info = process_card(image, card_key)
            
            if "your_card" in card_key:
                formatted_data["your_hand"].append(f"{card_info['value']} of {card_info['symbol']}")
                overlay.update_log(f"  🃏 Added to hand: {card_info['value']} of {card_info['symbol']}")
            else:
                formatted_data["table_cards"].append(f"{card_info['value']} of {card_info['symbol']}")
                overlay.update_log(f"  🌍 Added to community: {card_info['value']} of {card_info['symbol']}")
            
            captured_cards.add(card_key)
    

    
    overlay.update_log("✅ Phase processing complete")

def handle_alt5():
    """Handle Alt+5: Update balance, pot, and actions only"""
    """Manual update handler"""
    global current_phase
    formatted_data["game_phase"] = f"{PHASE_CONFIG[current_phase]['name']} (Raise)"
    overlay.update_log("\n🔃 MANUAL UPDATE TRIGGERED")

    # New: Auto-trigger AI analysis
    ai_decision = get_ai_decision()
    if ai_decision:
        overlay.update_log(f"🤖 AI action: {ai_decision['final_decision'].upper()}")
        overlay.update_log(f"💡 Reasoning: {ai_decision['thinking_process']}")
        perform_ai_action(ai_decision)
        return ai_decision

def rotate_image(image, angle):
    """Rotate the image by a given angle"""
    return image.rotate(angle, expand=True)

def normalize_action(text):
    """Standardize action text"""
    text = text.lower().strip()
    action_map = {
        r"\bcheck\b": "Check",
        r"\bcall\b": "Call",
        r"\bcal\b": "Call",  # Handle OCR typo
        r"\bfold\b": "Fold",
        r"\braise\s+(\d+)\b": "Raise \\1",  # Capture raise amount
        r"\braise\b": "Raise",  # Generic raise
        r"\bbet\b": "Bet"
    }
    for pattern, action in action_map.items():
        match = re.search(pattern, text)
        if match:
            # Handle raise amounts
            if "\\1" in action:
                amount = match.group(1)
                return f"Raise {amount}"
            return action
    return ""

def reset_game_state():
    global formatted_data, captured_cards, current_phase
    formatted_data = {
        "your_hand": [],
        "table_cards": [],
        "player_actions": defaultdict(
            lambda: {"current": "", "history": []},
            {
                "You": {"current": "", "history": []}
            }
        ),
        "your_balance": "",
        "pot": "",
        "phase": 1
    }
    captured_cards = set()
    current_phase = 1
    overlay.update_log("\n🔄 Game state completely reset")
    overlay.update_log("💠 All tracked data cleared")
    overlay.update_log("🃏 Ready for new hand")

def save_game_state():
    """Save current game state with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshots/game_state.json"
    
    # Convert defaultdicts to regular dicts
    def convert_to_serializable(obj):
        if isinstance(obj, defaultdict):
            return {k: convert_to_serializable(v) for k, v in obj.items()}
        return obj
    
    with open(filename, 'w') as f:
        serializable_data = convert_to_serializable(formatted_data)
        json.dump(serializable_data, f, indent=2, default=str)
    
    overlay.update_log(f"Game state saved to {filename}")
    print(f"Game state saved to {filename}")

def display_current_state():
    """Show current game state in console exactly matching JSON structure"""
    overlay.update_log("\nCurrent Game State:")
    print("\nCurrent Game State:")
    
    # Display cards in original format
    overlay.update_log(f"Your Hand: {formatted_data['your_hand']}")
    print(f"Your Hand: {formatted_data['your_hand']}")
    overlay.update_log(f"Community Cards: {formatted_data['table_cards']}")
    print(f"Community Cards: {formatted_data['table_cards']}")
    
    # Display player actions exactly as stored
    overlay.update_log("\nPlayer Actions:")
    print("\nPlayer Actions:")
    for player, data in formatted_data['player_actions'].items():
        overlay.update_log(f"  {player}:")
        print(f"  {player}:")
        
        # Show current action
        overlay.update_log(f"    Current: {data['current']}")
        print(f"    Current: {data['current']}")
        
        # Show full history
        overlay.update_log("    History:")
        print("    History:")
        for entry in data['history']:
            line = f"      Phase: {entry['phase']}, Action: {entry['action']}"
            overlay.update_log(line)
            print(line)
    
    # Display financial info
    overlay.update_log(f"\nYour Balance: {formatted_data['your_balance']}")
    print(f"\nBalance: {formatted_data['your_balance']}")
    overlay.update_log(f"Pot: {formatted_data['pot']}")
    print(f"Pot: {formatted_data['pot']}\n")

def get_ai_decision():
    global formatted_data
    try:
        with open("knowledge/knowledge.txt") as f:
            knowledge = f.read()
        overlay.update_log(f"🤖 AI analyzing game state...")
        print(formatted_data)
        decision = poker_ai_decision(formatted_data, knowledge)
        
        if "error" in decision:
            overlay.update_log(f"❌ AI Error: {decision['error']}")
            return None
        
        return decision
        
    except Exception as e:
        overlay.update_log(f"⚠️ AI Analysis Failed: {str(e)}")
        return None

def detect_condition(template_key, region_key, threshold=0.8):
    """Generic template detection function"""
    with mss.mss() as sct:
        region = COORDINATES[region_key]
        screenshot = np.array(sct.grab(region))
    
    if screenshot.shape[2] == 4:  # Handle alpha channel
        screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)
    else:
        screenshot = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
    
    result = cv2.matchTemplate(screenshot, TEMPLATES[template_key], cv2.TM_CCOEFF_NORMED)
    return np.max(result) > threshold

def is_ai_turn():
    return detect_condition("ai_turn", "ai_turn")

def is_round_end():
    return detect_condition("round_end", "round_end")

def is_new_hand_available():
    return detect_condition("new_hand", "new_hand")

def automation_loop():
    """Main automation control loop"""
    global ai_folded, round_active, automation_enabled, current_phase
    
    while automation_enabled:
        try:
            # Check round state
            if not round_active and is_new_hand_available():
                overlay.update_log("🃏 New hand detected")
                handle_phase(1)
                round_active = True
                ai_folded = False
                continue
                
            if is_ai_turn():
                overlay.update_log("🤖 AI's turn detected")
                ai_decision = None

                # First check for new phase triggers
                if current_phase == 2 and are_flop_cards_visible():
                    ai_decision = handle_phase(2)
                elif current_phase == 3 and is_turn_card_visible():
                    ai_decision = handle_phase(3)
                elif current_phase == 4 and is_river_card_visible():
                    ai_decision = handle_phase(4)
                # Then check for raises if no new phase was detected
                elif check_for_raises():
                    overlay.update_log("⚠️ Raise detected, triggering manual update")
                    ai_decision = handle_alt5()

                if ai_decision and isinstance(ai_decision, dict):
                    ai_folded = ai_decision.get("final_decision", "").lower() == "fold"
                    time.sleep(2)
                else:
                    overlay.update_log("⚠️ No valid AI decision received")
                    ai_folded = False  
                         
            # Check round end
            if is_round_end():
                overlay.update_log("🎉 Round end detected")
                handle_round_end()
                round_active = False
                time.sleep(10)

            time.sleep(1)
            
        except Exception as e:
            overlay.update_log(f"Automation error: {str(e)}")
            time.sleep(5)

# New card detection functions
def are_flop_cards_visible():
    """Check if all three flop cards are present"""
    return detect_condition("flop_cards", "flop_cards")

def is_turn_card_visible():
    """Check if turn card is visible"""
    return detect_condition("turn_card", "turn_card")

def is_river_card_visible():
    """Check if river card is visible"""
    return detect_condition("river_card", "river_card")

def update_game_state():
    global current_phase
    config = PHASE_CONFIG[current_phase]  # ADD THIS LINE TO GET CURRENT PHASE CONFIG
    formatted_data["game_phase"] = f"{config['name']}"
    overlay.update_log("\n🔃 Update game state")
    active_players = []
    
    # Check for new folds first
    for player in ["player1", "player2", "player3", "player4"]:
        player_key = player.capitalize()
        fold_key = f"{player}_fold"
        
        # Skip already folded players
        if any(entry.get("action") == "Fold" 
               for entry in formatted_data["player_actions"].get(player_key, {}).get("history", [])):
            overlay.update_log(f"  ⏩ {player_key} already folded")
            continue
            
        if fold_key in COORDINATES:
            fold_image = capture_screenshot(COORDINATES[fold_key], fold_key)
            if detect_fold(fold_image, player_key):
                player_actions = formatted_data["player_actions"].get(player_key, {"current": "", "history": []})
                # Only add fold entry if not already exists
                if not any(entry.get("action") == "Fold" for entry in player_actions["history"]):
                    player_actions["history"].append({
                        "phase": f"Phase {current_phase}",
                        "action": "Fold",
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })
                    player_actions["current"] = "Fold"
                    formatted_data["player_actions"][player_key] = player_actions
                    overlay.update_log(f"  🚫 {player_key} marked as folded")
            else:
                active_players.append(player_key)

    infer_missing_actions()  # Handles historical actions
    

    # Rest of processing only for active players
    overlay.update_log(f"👥 Active players: {', '.join(active_players) or 'None'}")
    overlay.update_log(f"📊 Processing {len(config['always_capture'])} interface elements")
    
    for field_key in config['always_capture']:
        if "actions" in field_key:
            player_from_key = field_key.split("_")[0].capitalize()
            if player_from_key not in active_players:
                overlay.update_log(f"  ⏩ Skipping {field_key} - player folded")
                continue
        
        # CAPTURE AND PROCESS FIELD DATA
        image = capture_screenshot(COORDINATES[field_key], field_key)
        processed_value = process_interface_field(image, field_key)
        
        if field_key == "your_balance":
            formatted_data["your_balance"] = processed_value
        elif field_key == "pot":
            formatted_data["pot"] = processed_value

    update_current_action_status()  # Handles current status

def check_for_raises():
    """Check if any player raised"""
    update_game_state()
    save_game_state()
    display_current_state()
    overlay.update_log("✅ Game state update complete")

    for player in formatted_data["player_actions"].values():
        current_action = player.get("current", "")
        if "Raise" in current_action or "Bet" in current_action:
            return True
    return False

def handle_round_end():
    """Handle end of round cleanup"""
    global ai_folded
    # Click to continue (coordinates may need adjustment)
    pyautogui.click(700, 700)  
    reset_game_state()
    overlay.update_log("🔄 Ready for new hand")

def toggle_automation():
    """Toggle automation on/off"""
    global automation_enabled
    automation_enabled = not automation_enabled
    status = "ENABLED" if automation_enabled else "DISABLED"
    overlay.update_log(f"🤖 Automation {status}")
    
    if automation_enabled:
        Thread(target=automation_loop, daemon=True).start()

def stop_program():
    overlay.update_log("\n🛑 Program stopped by user")
    overlay.root.destroy()  # Properly close the overlay window
    sys.exit(0)

def register_hotkeys():
    """Set up keyboard controls"""
    keyboard.add_hotkey("alt+a", toggle_automation)
    overlay.update_log("✅ Registered Alt+A - Toggle automation")
    keyboard.add_hotkey("esc", stop_program)
    overlay.update_log("✅ Registered Esc - Emergency stop")
    keyboard.add_hotkey("alt+1", lambda: handle_phase(1))
    overlay.update_log("✅ Registered Alt+1 - Capture hole cards")
    keyboard.add_hotkey("alt+2", lambda: handle_phase(2))
    overlay.update_log("✅ Registered Alt+2 - Capture flop")
    keyboard.add_hotkey("alt+3", lambda: handle_phase(3))
    overlay.update_log("✅ Registered Alt+3 - Capture turn")
    keyboard.add_hotkey("alt+4", lambda: handle_phase(4))
    overlay.update_log("✅ Registered Alt+4 - Capture river")
    keyboard.add_hotkey("alt+5", handle_alt5)
    overlay.update_log("✅ Registered Alt+5 - Manual update")
    overlay.update_log("🔥 All hotkeys ready")

if __name__ == "__main__":
    initialize_environment()
    # Register hotkeys first
    register_hotkeys()
    # Start keyboard listener in a background thread
    keyboard_thread = Thread(target=keyboard.wait)
    keyboard_thread.daemon = True
    keyboard_thread.start()
    # Run the Tkinter overlay in the main thread
    overlay.run()
