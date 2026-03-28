import base64
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()
import mss
import uvicorn

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from openai import OpenAI

# ---------------------------------------------------------------------------
# OpenAI-compatible client pointed at Anthropic's API
# ---------------------------------------------------------------------------
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

client = OpenAI(
    base_url="https://api.anthropic.com/v1",
    api_key=api_key,
)

MODEL = "claude-sonnet-4-6"

app = FastAPI(title="Wingman AI Game Assistant")

# Allow the Tauri frontend (served from a local origin) to call this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper: capture the primary monitor and return raw PNG bytes
# ---------------------------------------------------------------------------
def capture_screen_png() -> bytes:
    """Grab the primary monitor with mss and return raw PNG bytes."""
    with mss.mss() as sct:
        # monitor index 1 is the primary display
        screenshot = sct.grab(sct.monitors[1])
        return mss.tools.to_png(screenshot.rgb, screenshot.size)


# ---------------------------------------------------------------------------
# Helper: capture the primary monitor and return a base64 PNG data-URI
# ---------------------------------------------------------------------------
def capture_screen_base64() -> str:
    """Grab the primary monitor with mss and return a base64-encoded PNG data URI."""
    encoded = base64.b64encode(capture_screen_png()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


# ---------------------------------------------------------------------------
# Helper: send a screenshot + prompt to the VLM and parse the JSON response
# ---------------------------------------------------------------------------
def ask_vlm(prompt: str) -> dict:
    """
    Capture the screen, send it alongside *prompt* to the vision model,
    and return the parsed JSON object from the model's reply.
    """
    image_url = capture_screen_base64()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    raw = response.choices[0].message.content.strip()

    # First try parsing the whole response as JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fallback: extract the first {...} block from the response
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise HTTPException(
        status_code=502,
        detail=f"Model returned non-JSON response: {raw!r}",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

HINT_PROMPT = (
    "Look at the screenshot. "
    "Return ONLY a valid JSON object with 'hint_text' (a short 1-sentence hint on what to do), "
    "'target_x' (integer X pixel coordinate of the object of interest), "
    "and 'target_y' (integer Y pixel coordinate). "
    "Do not wrap the JSON in markdown blocks."
)

AUTOPLAY_PROMPT = (
    "Look at the screenshot. "
    "Identify the next logical action to progress in the game. "
    "Your response must be a single JSON object and nothing else — no explanation, no preamble, no markdown. "
    "Start your response with '{' and end it with '}'. "
    "Return ONLY a valid JSON object with the following fields: "
    "'action' (one of: 'click', 'double_click', 'move', 'drag', 'key_press', 'key_hold', or 'wait'), "
    "'target_x' (integer X pixel coordinate — required for click, double_click, move, drag), "
    "'target_y' (integer Y pixel coordinate — required for click, double_click, move, drag), "
    "'end_x' (integer X drag destination — only for drag), "
    "'end_y' (integer Y drag destination — only for drag), "
    "'key' (string key name — required for key_press and key_hold), "
    "'description' (a short human-readable summary of what this action does, e.g. 'Click the Start button'), "
    "'reason' (a concise explanation of why this is the best next action given the current game state). "
    "For 'key' use standard key names: movement keys 'w', 'a', 's', 'd', "
    "arrow keys 'up', 'down', 'left', 'right', "
    "action keys 'space', 'enter', 'escape', 'shift', 'ctrl', 'tab', 'e', 'r', 'f', 'q', "
    "or any other relevant key for the game. "
    "Use 'key_hold' when the key should be held (e.g. sustained movement), 'key_press' for a single tap. "
    "Omit action-specific fields that are not relevant to the chosen action, but always include 'description' and 'reason'. "
    "Do not wrap the JSON in markdown blocks."
)


@app.get("/hint")
def hint():
    """
    Capture the screen and ask the VLM for a one-sentence gameplay hint
    along with the pixel coordinates of the object of interest.

    Returns:
        {
            "hint_text": str,
            "target_x":  int,
            "target_y":  int
        }
    """
    return ask_vlm(HINT_PROMPT)


@app.get("/screenshot", response_class=Response)
def screenshot():
    """
    Capture the primary monitor and return it as a PNG image.
    Open this URL directly in a browser to see exactly what the model sees.
    """
    return Response(content=capture_screen_png(), media_type="image/png")


@app.get("/autoplay")
def autoplay():
    """
    Capture the screen and ask the VLM for the next action to take.
    The Tauri frontend is responsible for executing the action.

    Returns:
        {
            "action":      "click" | "double_click" | "move" | "drag" | "key_press" | "key_hold" | "wait",
            "target_x":    int   (for click, double_click, move, drag),
            "target_y":    int   (for click, double_click, move, drag),
            "end_x":       int   (for drag),
            "end_y":       int   (for drag),
            "key":         str   (for key_press, key_hold),
            "description": str   (human-readable summary of the action),
            "reason":      str   (explanation of why this action was chosen)
        }
    """
    return ask_vlm(AUTOPLAY_PROMPT)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
