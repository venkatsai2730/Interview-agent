import asyncio, base64, json, math, os, struct, sys

def load_api_key():
    try:
        for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
            if line.strip().startswith("SARVAM_API_KEY="):
                return line.strip().split("=",1)[1].strip().strip('"').strip("'")
    except: pass
    return os.environ.get("SARVAM_API_KEY","")

def gen_pcm(ms=2000, sr=16000):
    n = int(sr*ms/1000)
    return struct.pack(f"<{n}h", *[int(32767*0.3*math.sin(2*math.pi*440*i/sr)) for i in range(n)])

def to_wav(pcm, sr=16000):
    import io; b=io.BytesIO(); ds=len(pcm)
    b.write(b'RIFF'); b.write(struct.pack('<I',36+ds)); b.write(b'WAVE')
    b.write(b'fmt '); b.write(struct.pack('<IHHIIHH',16,1,1,sr,sr*2,2,16))
    b.write(b'data'); b.write(struct.pack('<I',ds)); b.write(pcm)
    return b.getvalue()

async def test(api_key, codec, enc, label):
    import websockets
    url = (f"wss://api.sarvam.ai/speech-to-text/ws"
           f"?model=saaras:v3&mode=transcribe&language-code=en-IN"
           f"&sample_rate=16000&input_audio_codec={codec}"
           f"&high_vad_sensitivity=true&vad_signals=true")
    headers = {"Api-Subscription-Key": api_key}
    print(f"\n=== {label} ===\ncodec={codec}  encoding={enc}")

    # Try both websockets header APIs (handles old and new versions)
    ws = None
    try:
        try:
            ws = await websockets.connect(url, additional_headers=headers, open_timeout=10)
        except TypeError:
            ws = await websockets.connect(url, extra_headers=headers, open_timeout=10)
        print("  WebSocket: CONNECTED")
    except Exception as e:
        print(f"  CONNECT FAILED: {type(e).__name__}: {e}")
        return

    try:
        pcm = gen_pcm()
        chunks = [pcm[i:i+640] for i in range(0, len(pcm), 640)]  # 20ms chunks
        for c in chunks:
            d = to_wav(c) if enc == "audio/wav" else c
            await ws.send(json.dumps({"audio": {"data": base64.b64encode(d).decode(), "encoding": enc, "sample_rate": 16000}}))
        await ws.send(json.dumps({"type": "flush"}))
        print(f"  Sent {len(chunks)} chunks + flush. Waiting for response...")

        msgs = []
        try:
            while True:
                r = await asyncio.wait_for(ws.recv(), timeout=6)
                d = json.loads(r)
                msgs.append(d)
                print(f"  MSG: {d}")
        except asyncio.TimeoutError:
            pass

        transcripts = [m for m in msgs if m.get("type") == "transcript"]
        if transcripts:
            print(f"  RESULT: ✅ WORKING — got {len(transcripts)} transcript(s)")
        elif msgs:
            print(f"  RESULT: ❌ NO TRANSCRIPTS — got {len(msgs)} other msgs: {[m.get('type') for m in msgs]}")
        else:
            print(f"  RESULT: ❌ SILENT — no messages at all in 6 seconds")
    finally:
        await ws.close()

async def main():
    k = load_api_key()
    if not k: print("ERROR: SARVAM_API_KEY not found"); return
    print(f"API Key: {k[:8]}...")
    await test(k, "pcm_s16le", "pcm_s16le", "TEST 1: pcm_s16le (current code)")
    await asyncio.sleep(2)
    await test(k, "wav", "audio/wav", "TEST 2: wav-per-chunk (what AI keeps switching to)")
    print("\n=== DONE — whichever shows WORKING is the correct setting ===")

asyncio.run(main())
