#!/opt/connector/bin/python

import os
import sys

# Add the parent directory to sys.path when running directly
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from services.connector import Connector
    from services.service import Service
else:
    from .connector import Connector
    from .service import Service

from logger import get_logger
import subprocess
import tempfile
from google.cloud import texttospeech
from google.oauth2 import service_account
from typing import Optional, Dict, Any

from pytimeparse.timeparse import timeparse


# Get logger for this module
logger = get_logger(__name__)

class GoogleTTSConnector(Connector):
    """Connector for Google Text-to-Speech that sends audio to a HomePod via raop_play."""
    
    def __init__(self, tts: 'GoogleTTS', text: str):
        super().__init__()
        logger.info(f"TTS Connector created for {text=}")
        self.tts = tts
        self.text = text
        self.name = f"GoogleTTS<{text}>"
    
    def _set_action(self, value: bool) -> None:
        """Override _set_action to play the synthesized audio on HomePod using pipes."""
        logger.info(f"Running TTS command {self.text=}")
        try:
            if not value:
                return
            # Get processed audio directly from synthesize_speech
            self.tts.speak(self.text)
            
        except Exception as e:
            logger.error(f"Error in TTS playback: {str(e)}")
        finally:
            # Reset state after playback completes or on error
            self.set(False, act=False)

class GoogleTTS(Service):
    """Service for Google Cloud Text-to-Speech integration."""
    
    def __init__(self, homepod_ip: str, volume: 80, play_command: str = './services/libraop/build/raop_play-linux-aarch64', credentials: Optional[Dict[str, Any]] = None, credentials_file: Optional[str] = None, after="00:00", before= "24:00"):
        """
        Initialize Google TTS service.
        
        Args:
            homepod_ip: IP address of the target HomePod
            credentials: Optional dictionary containing Google Cloud service account credentials.
                        If not provided, will use default credentials.
                        Required keys: type, project_id, private_key_id, private_key, client_email, client_id
            credentials_file: Optional path to a JSON file containing the credentials.
                            If both credentials and credentials_file are provided, credentials takes precedence.
        """
        super().__init__()

        self.homepod_ip = homepod_ip
        self.volume = volume
        self.play_command = play_command
        self.after = timeparse(after, granularity="minutes")
        self.before = timeparse(before, granularity="minutes")
        
        # Initialize credentials if provided
        if credentials:
            creds = service_account.Credentials.from_service_account_info(credentials)
            self.client = texttospeech.TextToSpeechClient(credentials=creds)
        elif credentials_file:
            creds = service_account.Credentials.from_service_account_file(credentials_file)
            self.client = texttospeech.TextToSpeechClient(credentials=creds)
        else:
            self.client = texttospeech.TextToSpeechClient()
    
    def _is_hebrew(self, text: str) -> bool:
        """Check if the text contains Hebrew characters."""
        # Hebrew Unicode range: \u0590-\u05FF
        return any('\u0590' <= char <= '\u05FF' for char in text)
    
    def get_voice_params(self, text: str) -> tuple[texttospeech.VoiceSelectionParams, texttospeech.AudioConfig]:
        """Get appropriate voice parameters based on text language."""
        if self._is_hebrew(text):
            voice = texttospeech.VoiceSelectionParams(
                language_code="he-IL",
                name="he-IL-Wavenet-A"  # Using WaveNet voice for Hebrew as Neural2 is not available
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                speaking_rate=1.2,  
                pitch=0.0
            )
        else:
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-US",
                name="en-US-Chirp-HD-D"
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                speaking_rate=1,  
                pitch=0.0
            )
        return voice, audio_config

    def synthesize_speech(self, text: str, output_file: str = None) -> bytes:
        """
        Synthesize speech from text and process with ffmpeg.
        If output_file is provided, save to file. Otherwise return processed audio bytes.
        
        Args:
            text: The text to convert to speech. If text starts with <speak>, it will be treated as SSML.
            output_file: Optional path to save the processed audio file
            
        Returns:
            bytes: The processed audio data if output_file is None
        """
        try:
            # Check if input is SSML
            if text.strip().lower().startswith('<speak>'):
                logger.debug("Using ssml")
                synthesis_input = texttospeech.SynthesisInput(ssml=text)
            else:
                logger.debug("Using text")
                synthesis_input = texttospeech.SynthesisInput(text=text)
            
            # Get voice parameters from service
            voice, audio_config = self.get_voice_params(text)
            
            # Perform the text-to-speech request
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            
            # Process audio with ffmpeg using pipes
            ffmpeg_cmd = ['/bin/ffmpeg', '-i', '-', '-ar', '44100', '-ac', '2', 
                         '-sample_fmt', 's16', '-f', 'wav']
            
            if output_file:
                ffmpeg_cmd.append(output_file)
                subprocess.run(ffmpeg_cmd, input=response.audio_content, check=True)
                logger.info(f"Processed audio saved to: {output_file}")
                return None
            else:
                ffmpeg_cmd.append('-')  # Output to stdout
                process = subprocess.run(ffmpeg_cmd, input=response.audio_content, 
                                      capture_output=True, check=True)
                return process.stdout
                
        except Exception as e:
            logger.error(f"Error synthesizing speech: {str(e)}")
            raise
    
    def device(self, text: str) -> GoogleTTSConnector:
        """Create a new TTS connector for a specific HomePod."""
        return GoogleTTSConnector(self, text)

    def speak(self, text: str):
        audio_data = self.synthesize_speech(text)
        
        # Play the processed audio on HomePod using pipes
        cmd = [self.play_command, self.homepod_ip, "-v", str(self.volume), "-"]
        logger.info(f"Playing audio on HomePod {self.homepod_ip} {self.volume}")
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        process.communicate(input=audio_data)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <homepod_ip> \"message to speak\"")
        sys.exit(1)
        
    homepod_ip = sys.argv[1]
    message = sys.argv[2]
    
    try:
        # Configure logger for debug level when running directly
        from logger import setup_logger, get_logger
        setup_logger()
        logger = get_logger(__name__)
        logger.info("Starting home automation connector")
        
        # For testing, we'll use the credentials file directly
        credentials_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "homekitai-58ec470d4bd3.json")
        tts_service = GoogleTTS(homepod_ip, 50, credentials_file=credentials_path)
        
        # Create a connector for the specified HomePod
        connector = tts_service.device(text=message)
        
        # Speak the message
        connector.set(True)
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1) 
