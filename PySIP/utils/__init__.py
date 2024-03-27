async def generate_audio(text: str, voice: str) -> io.BytesIO:
    """
    this genertes the real TTS using edge_tts for this part.
    """
    com = Communicate(text, voice)
    temp_chunk = io.BytesIO()
    async for chunk in com.stream():
        if chunk['type'] == 'audio':
            await asyncio.to_thread(temp_chunk.write, chunk['data'])

    await asyncio.to_thread(temp_chunk.seek, 0)
    decoded_audio = await asyncio.to_thread(mp3_to_wav, temp_chunk) 
    return decoded_audio
