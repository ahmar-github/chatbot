import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import types

# 1. Load environment variables
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY is missing from environment variables or .env file.")

# 2. Initialize Gemini Client
client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-2.5-flash"

app = FastAPI()

# 3. Enable CORS for local HTML frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- IN-MEMORY DATABASE ---
admins = ["admin@system.com"]
users_db = {}

# --- DATABASE FUNCTIONS ---
# Functions include type hints and docstrings so Gemini automatically extracts tool parameters
def add_user(email: str, phone: str = "Unknown") -> str:
    """Add a new user to the system with their email address and optional phone number."""
    users_db[email] = {"email": email, "phone": phone, "city": "Unknown"}
    return f"User '{email}' added successfully."

def remove_user(email: str) -> str:
    """Remove an existing user from the system using their email address."""
    if email in users_db:
        del users_db[email]
        return f"User '{email}' removed successfully."
    return f"User '{email}' was not found in the database."

def update_user(name: str, city: str) -> str:
    """Update a user's city location based on their name or email keyword."""
    for email in users_db.keys():
        if name.lower() in email.lower():
            users_db[email]["city"] = city
            return f"Updated {email}'s city to '{city}'."
    return f"Could not find any user matching name '{name}'."

# --- SCHEMAS ---
class LoginRequest(BaseModel):
    email: str

class ChatRequest(BaseModel):
    message: str

# --- ROUTES ---
@app.post("/login")
def login(req: LoginRequest):
    if req.email in admins:
        return {"status": "success", "message": "Authentication successful"}
    raise HTTPException(status_code=401, detail="Unauthorized admin email.")

@app.post("/chat")
def chat(req: ChatRequest):
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=req.message,
            config=types.GenerateContentConfig(
                system_instruction="You are a database administrative assistant. Convert user instructions into database function calls.",
                tools=[add_user, remove_user, update_user],
                temperature=0.1,
            )
        )

        # Handle Function Calling
        if response.function_calls:
            tool_call = response.function_calls[0]
            func_name = tool_call.name
            args = tool_call.args or {}

            if func_name == "add_user":
                reply = add_user(
                    email=str(args.get("email", "")),
                    phone=str(args.get("phone", "Unknown"))
                )
            elif func_name == "remove_user":
                reply = remove_user(
                    email=str(args.get("email", ""))
                )
            elif func_name == "update_user":
                reply = update_user(
                    name=str(args.get("name", "")),
                    city=str(args.get("city", ""))
                )
            else:
                reply = "Unknown tool call requested."

            return {"reply": reply, "db_state": users_db, "model_used": MODEL_NAME}

        if response.text:
            return {"reply": response.text, "db_state": users_db, "model_used": MODEL_NAME}

        return {"reply": "Command processed.", "db_state": users_db, "model_used": MODEL_NAME}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))