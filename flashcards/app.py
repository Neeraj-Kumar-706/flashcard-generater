from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.debug = True  # Enable debug mode


def sanitize_key(k: str) -> str:
    """Strip surrounding quotes and whitespace from keys loaded from .env."""
    if not k:
        return k
    s = k.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1].strip()
    return s


GOOGLE_API_KEY = sanitize_key(os.getenv('GOOGLE_API_KEY'))
print("[DEBUG] Checking for API key...")
if not GOOGLE_API_KEY:
    print("[DEBUG] API key not found in environment variables; running in locked mode until key is provided via web UI")

# Helper: preferred candidates in order (common variants across versions)
candidates = [
    'gemini-pro',
    'gemini-1.0-pro',
    'gemini-1.0',
    'gemini',
    'text-bison',
    'chat-bison',
]

def pick_model(names):
    # prefer known generative candidates
    for c in candidates:
        for name in names:
            if c in name:
                return name
    # otherwise pick first non-embedding model
    for name in names:
        ln = name.lower()
        if 'embed' not in ln and 'embedding' not in ln and 'vector' not in ln:
            return name
    # fallback to first if nothing else
    return names[0] if names else None


if GOOGLE_API_KEY:
    try:
        # Configure the Gemini API
        genai.configure(api_key=GOOGLE_API_KEY)

        # Discover available models and pick a suitable text/generative model
        available_models = genai.list_models()
        model_names = [m.name for m in available_models]
        print("[DEBUG] Available models:", model_names)

        chosen = pick_model(model_names)

        if not chosen:
            raise Exception('No generative models available for this API key')

        print(f"[DEBUG] Chosen model: {chosen}")

        # Set up model configuration
        generation_config = {
            "temperature": 0.7,
            "top_p": 1,
            "top_k": 40,
            "max_output_tokens": 1024,
        }

        # Initialize the model with chosen name
        model = genai.GenerativeModel(model_name=chosen, generation_config=generation_config)
        print("[DEBUG] Successfully initialized Gemini model")
    except Exception as e:
        print(f"[DEBUG] Error configuring Gemini: {str(e)}")
        # Mark Gemini as not ready and continue so the app can return a helpful error
        GEMINI_READY = False
        print("[DEBUG] Gemini initialization failed, continuing with GEMINI_READY=False")
    else:
        GEMINI_READY = True
else:
    GEMINI_READY = False

def is_gemini_ready():
    return GEMINI_READY

def validate_api_key():
    """Validate the API key by making a minimal API call"""
    try:
        # Make a simple test request against the chosen model
        test_prompt = "Return only the word OK"
        try:
            test_response = model.generate_content(test_prompt)
        except Exception as e:
            # If the model doesn't support generate_content, log and return False
            print(f"[DEBUG] Model generate_content failed: {e}")
            return False

        # normalize response content
        result = None
        if hasattr(test_response, 'text') and test_response.text:
            result = test_response.text.strip().upper()
        elif hasattr(test_response, 'output'):
            try:
                parts = []
                for item in test_response.output:
                    if isinstance(item, dict) and 'content' in item:
                        parts.append(item['content'])
                    elif isinstance(item, str):
                        parts.append(item)
                result = '\n'.join(parts).strip().upper()
            except Exception:
                result = None

        is_valid = result == "OK"

        if is_valid:
            print("[DEBUG] API key validated successfully")
        else:
            print(f"[DEBUG] Unexpected model validation result: {result}")

        return is_valid
    except Exception as e:
        print(f"[DEBUG] API key validation failed: {str(e)}")
        return False



def generate_flashcards(topic, level):
    """Main function to generate proper Q&A flashcards"""
    print(f"\n[DEBUG] Starting flashcard generation for topic: {topic}, level: {level}")

    try:
        # Create structured prompt for Gemini
        prompt = f"""You are an expert educational content creator. Create 6 flashcards about {topic} for {level} level students.

        Follow these requirements carefully:
        1. Create exactly 6 unique flashcards
        2. Each card must focus on a different aspect:
        3. Match {level} level complexity
        4. Questions must be clear and specific
        5. Answers must be 2-3 sentences, informative but concise
        
        Respond ONLY with a JSON array in this exact format:
        [
            {{"question": "Specific question?", "answer": "Clear, concise answer."}}
        ]

        Include exactly 6 cards. Do not include any other text or explanations.
        """

        print("[DEBUG] Sending request to Gemini with safe wrapper...")
        # Use a safe wrapper to call Gemini and enforce a short timeout
        try:
            response = model.generate_content(prompt)
        except Exception as e:
            print(f"[DEBUG] Gemini request failed: {e}")
            raise Exception("Gemini API request failed")

        # Some Gemini client builds return `.text` or `.output` - normalize
        content = None
        if hasattr(response, 'text') and response.text:
            content = response.text
        elif hasattr(response, 'output'):
            # `output` may be a list of message objects
            try:
                # join any string parts
                parts = []
                for item in response.output:
                    if isinstance(item, dict) and 'content' in item:
                        parts.append(item['content'])
                    elif isinstance(item, str):
                        parts.append(item)
                content = '\n'.join(parts).strip()
            except Exception:
                content = None

        if not content:
            print("[DEBUG] Gemini returned no content or an unexpected format")
            raise Exception("Empty or malformed response from Gemini")

        print(f"[DEBUG] Received response: {content[:200]}...")
        
        # Parse the response
        try:
            # Clean up the response if needed (remove markdown code blocks if present)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()
            
            flashcards = json.loads(content)
            if isinstance(flashcards, list) and len(flashcards) > 0:
                # Ensure each card has the required fields
                validated_cards = []
                for card in flashcards:
                    if isinstance(card, dict) and 'question' in card and 'answer' in card:
                        validated_cards.append({
                            'question': str(card['question']).strip(),
                            'answer': str(card['answer']).strip()
                        })
                
                # Ensure we have exactly 6 cards
                while len(validated_cards) < 6:
                    validated_cards.append({
                        'question': f'What is another aspect of {topic}?',
                        'answer': f'This is another important aspect of {topic} that helps in understanding the concept better.'
                    })
                
                validated_cards = validated_cards[:6]  # Limit to 6 cards
                print(f"[DEBUG] Successfully validated {len(validated_cards)} flashcards")
                return validated_cards
            else:
                raise ValueError("Invalid response format")
        except json.JSONDecodeError as e:
            print(f"[DEBUG] JSON parsing error: {str(e)}")
            raise Exception("Failed to parse AI response")
        except Exception as e:
            print(f"[DEBUG] Error processing flashcards: {str(e)}")
            raise
        

        


    except Exception as e:
        print(f"[DEBUG] Error in generate_flashcards: {str(e)}")
        raise  # Re-raise the exception to be handled by the route handler

@app.route('/')
def home():
    print("[DEBUG] Rendering home page")
    # If no API key is configured, instruct frontend to open settings modal
    return render_template('index.html', open_settings=(not bool(GOOGLE_API_KEY)))

@app.route('/generate', methods=['POST'])
def create_flashcards():
    print("\n[DEBUG] Received /generate POST request")
    
    try:
        # Short-circuit if Gemini was not initialized at startup
        if not is_gemini_ready():
            print("[DEBUG] Gemini not ready, rejecting request quickly")
            return jsonify({
                "success": False,
                "error": "Gemini service unavailable. Check server logs and your GOOGLE_API_KEY.",
                "flashcards": []
            }), 503

        data = request.json
        print(f"[DEBUG] Request data: {data}")
        
        topic = data.get('topic', '').strip()
        level = data.get('level', 'beginner').strip()
        print(f"[DEBUG] Topic: {topic}, Level: {level}")
        
        # Clear any cached data
        if hasattr(app, '_cached_responses'):
            delattr(app, '_cached_responses')
            print("[DEBUG] Cleared cached responses")
        
        if not topic:
            print("[DEBUG] Error: No topic provided")
            return jsonify({
                "success": False,
                "error": "Please provide a topic",
                "flashcards": []
            }), 400

        # Generate flashcards
        flashcards = generate_flashcards(topic, level)
        
        if not flashcards:
            print("[DEBUG] generate_flashcards returned no data")
            return jsonify({
                "success": False,
                "error": "No flashcards were generated",
                "flashcards": []
            }), 500

        print(f"[DEBUG] Generated {len(flashcards)} flashcards")
        # dump full flashcards for debugging (truncate long answers)
        for i, card in enumerate(flashcards):
            q = card.get('question', '')[:200]
            a = card.get('answer', '')[:200]
            print(f"[DEBUG] Card {i + 1}: Q: {q} | A: {a}")

        return jsonify({
            "success": True,
            "flashcards": flashcards
        })

    except Exception as e:
        error_msg = f"Error in create_flashcards: {str(e)}"
        print(f"[DEBUG] {error_msg}")
        return jsonify({
            "success": False,
            "error": error_msg,
            "flashcards": []
        }), 500


@app.route('/update-key', methods=['POST'])
def update_key():
    """Save GOOGLE_API_KEY to .env and attempt to reconfigure Gemini."""
    try:
        data = request.json or {}
        key = data.get('key', '').strip()
        if not key:
            return jsonify({"success": False, "error": "Missing key"}), 400

        # Write to .env (append/replace logic) - ensure the key is quoted
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()

        # sanitize key: remove any surrounding quotes and forbid newlines
        sanitized = key.strip()
        if (sanitized.startswith('"') and sanitized.endswith('"')) or (sanitized.startswith("'") and sanitized.endswith("'")):
            sanitized = sanitized[1:-1].strip()
        # Prevent writing multiline or obviously invalid keys
        if '\n' in sanitized or '\r' in sanitized:
            return jsonify({"success": False, "error": "Invalid API key format"}), 400

        quoted = f'"{sanitized}"'

        found = False
        for i, line in enumerate(lines):
            if line.startswith('GOOGLE_API_KEY='):
                lines[i] = f'GOOGLE_API_KEY={quoted}'
                found = True
                break

        if not found:
            lines.append(f'GOOGLE_API_KEY={quoted}')

        # write atomically
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        # Reload env and reconfigure genai
        load_dotenv(dotenv_path=env_path, override=True)
        global GOOGLE_API_KEY, GEMINI_READY, model
        GOOGLE_API_KEY = sanitize_key(os.getenv('GOOGLE_API_KEY'))
        try:
            # ensure genai gets the sanitized/unquoted key
            genai.configure(api_key=GOOGLE_API_KEY)
            # Attempt to re-list models and reinitialize
            available_models = genai.list_models()
            model_names = [m.name for m in available_models]
            print("[DEBUG] Available models after update:", model_names)

            # pick a suitable model (reuse pick_model defined at startup)
            try:
                chosen = pick_model(model_names)
            except Exception:
                chosen = model_names[0] if model_names else None

            if not chosen:
                GEMINI_READY = False
                return jsonify({"success": False, "error": "No generative models available for this key"}), 500

            print(f"[DEBUG] Chosen model after update: {chosen}")
            generation_config = {"temperature":0.7, "max_output_tokens":1024, "top_p":1, "top_k":40}
            model = genai.GenerativeModel(model_name=chosen, generation_config=generation_config)
            GEMINI_READY = True
        except Exception as e:
            print(f"[DEBUG] Reconfigure after update failed: {e}")
            GEMINI_READY = False
            return jsonify({"success": False, "error": f"Failed to configure Gemini: {e}"}), 500

        return jsonify({"success": True, "message": "API key updated and Gemini reconfigured"})

    except Exception as e:
        print(f"[DEBUG] update_key error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)