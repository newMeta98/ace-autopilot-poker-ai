# utils/api_client.py
from openai import OpenAI
import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

def poker_ai_decision(game_state, knowledge):
    """
    Get AI decision for current poker game state
    Returns structured analysis and decision in specified JSON format
    """
    print("AI analyzing game state...\n")
    api_key = os.getenv('DEEPSEEK_API_KEY')
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    game_state_phase = game_state['game_phase']
    system_prompt = f"""You are a professional poker AI player. 
    You are known for taking calculated risks, and wining. 
    You dont fold if noone raises, but you check and wait to see next cards, 
    you also call small rases if you want to see what card are coming to the table 
    (if you think you have potencial). 
    Current phase: {game_state_phase}
    Analyze the current game state using:
1. Provided poker knowledge
2. Current game state details
3. Advanced poker theory
4. Probabilistic calculations

Generate response in EXACTLY this JSON format:"""

    example_output = '''
    {
        "thinking_process": "(step-by-step reasoning)",
        "grid_structure": "(13×13 Hand Grid analysis)",
        "hand_combinations": "(possible hand combinations calculation)",
        "range_analysis": "(opponent range analysis)",
        "equity_calculations": "(equity calculations vs ranges)",
        "decision_making": "(decision process explanation)",
        "final_decision": "(check|fold|raise|all_in|call)"
    }'''

    messages = [
        {
            "role": "system",
            "content": f"{system_prompt}\n{example_output}\n\nPoker Knowledge:\n{knowledge}"
        },
        {
            "role": "user",
            "content": f"Current Game State:\n{json.dumps(game_state, indent=2)}"
        }
    ]

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.3,
            response_format={'type': 'json_object'}
        )

        raw_response = response.choices[0].message.content
        logging.info(f"Raw API Response: {raw_response}")

        # Validate and parse response
        response_json = json.loads(raw_response)
        required_keys = [
            "thinking_process", "grid_structure", 
            "hand_combinations", "range_analysis",
            "equity_calculations", "decision_making",
            "final_decision"
        ]
        
        if not all(key in response_json for key in required_keys):
            raise ValueError("Missing required keys in AI response")

        valid_decisions = ["check", "fold", "raise", "all_in", "call"]
        if response_json["final_decision"].lower() not in valid_decisions:
            raise ValueError(f"Invalid decision: {response_json['final_decision']}")

        return response_json

    except json.JSONDecodeError as e:
        logging.error(f"JSON Parse Error: {e}\nResponse: {raw_response}")
        return {"error": "Failed to parse AI response"}
    except Exception as e:
        logging.error(f"AI Analysis Error: {e}")
        return {"error": str(e)}