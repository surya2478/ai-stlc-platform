"""FastAPI router for dynamic voiceover generation using gTTS."""
import io
import base64
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from gtts import gTTS

router = APIRouter()

class VoiceoverRequest(BaseModel):
    text: str
    lang: str = "en"
    tld: str = "co.in"

@router.post("/generate-voiceover", summary="Generate voiceover MP3 as Base64 data URL")
async def generate_voiceover(payload: VoiceoverRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    
    try:
        fp = io.BytesIO()
        # Generate speech using gTTS
        tts = gTTS(text=payload.text, lang=payload.lang, tld=payload.tld, slow=False)
        tts.write_to_fp(fp)
        fp.seek(0)
        
        # Encode to Base64
        audio_bytes = fp.read()
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        data_url = f"data:audio/mp3;base64,{audio_base64}"
        
        return {"audio_base64": data_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate voiceover: {str(e)}")
