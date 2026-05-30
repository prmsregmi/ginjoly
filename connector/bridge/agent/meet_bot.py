import asyncio
import base64
import struct
from pathlib import Path
from playwright.async_api import async_playwright

WORKLET_JS = (Path(__file__).parent.parent / "static" / "audio_worklet.js").read_text()
BOT_NAME = "Aria Notetaker"


async def join_meet(meeting_url: str, audio_callback, status_callback=None):
    """
    Joins a Google Meet as a guest bot.
    Calls audio_callback(pcm_bytes) with raw 16kHz mono int16 PCM.
    Calls status_callback(str) with status updates.
    """
    async def status(msg: str):
        print(f"[meet_bot] {msg}")
        if status_callback:
            await status_callback(msg)

    async with async_playwright() as pw:
        # Use real Chrome to avoid bot detection
        context = await pw.chromium.launch_persistent_context(
            user_data_dir="/tmp/aria-chrome-profile",
            channel="chrome",
            headless=False,
            args=[
                "--use-fake-ui-for-media-stream",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            permissions=["microphone", "camera"],
        )

        page = await context.new_page()
        await status("Navigating to meeting...")
        await page.goto(meeting_url)
        await page.wait_for_timeout(4000)

        # Dismiss any overlays (cookie consent, etc.)
        for text in ["Accept all", "Got it", "Dismiss"]:
            try:
                btn = page.get_by_role("button", name=text)
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

        # If Google asks to sign in, click "Continue as guest" / "Join as guest"
        for text in ["Continue as guest", "Join as a guest", "Use without an account"]:
            try:
                btn = page.get_by_role("button", name=text)
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        # Fill in the bot's display name
        try:
            name_input = page.locator("input[placeholder*='name' i], input[aria-label*='name' i]").first
            await name_input.wait_for(state="visible", timeout=5000)
            await name_input.fill(BOT_NAME)
            await page.wait_for_timeout(500)
        except Exception:
            pass

        # Click "Ask to join" (guest join goes to waiting room)
        for text in ["Ask to join", "Join now", "Join"]:
            try:
                btn = page.get_by_role("button", name=text)
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await status(f"Waiting to be admitted as '{BOT_NAME}'...")
                    break
            except Exception:
                pass

        # Wait until actually inside the meeting (mic button appears)
        try:
            await page.locator("[data-is-muted], [aria-label*='microphone' i], [aria-label*='mic' i]").first.wait_for(
                state="visible", timeout=120000  # host has 2 min to admit
            )
        except Exception:
            await status("Timed out waiting to be admitted")
            return

        await status("Admitted to meeting — starting audio capture...")
        await page.wait_for_timeout(2000)

        # Inject AudioWorklet to capture incoming audio
        worklet_b64 = base64.b64encode(WORKLET_JS.encode()).decode()
        await page.evaluate(f"""
            async () => {{
                const ctx = new AudioContext({{ sampleRate: 16000 }});
                const dest = ctx.createMediaStreamDestination();

                // Capture audio from all media elements (remote participants)
                const hookElement = (el) => {{
                    try {{
                        const src = ctx.createMediaElementSource(el);
                        src.connect(dest);
                        src.connect(ctx.destination);
                    }} catch(e) {{}}
                }};

                document.querySelectorAll('audio, video').forEach(hookElement);

                // Also watch for new elements added by Meet
                new MutationObserver((mutations) => {{
                    mutations.forEach(m => m.addedNodes.forEach(n => {{
                        if (n.tagName === 'AUDIO' || n.tagName === 'VIDEO') hookElement(n);
                    }}));
                }}).observe(document.body, {{ childList: true, subtree: true }});

                const workletBlob = new Blob(
                    [atob('{worklet_b64}')],
                    {{ type: 'application/javascript' }}
                );
                await ctx.audioWorklet.addModule(URL.createObjectURL(workletBlob));

                const workletNode = new AudioWorkletNode(ctx, 'audio-capture-processor');
                dest.stream.getAudioTracks().forEach(track => {{
                    ctx.createMediaStreamSource(new MediaStream([track])).connect(workletNode);
                }});

                workletNode.port.onmessage = (e) => {{
                    window._audioChunks = window._audioChunks || [];
                    window._audioChunks.push(Array.from(new Int16Array(e.data)));
                }};

                window._audioCaptureStarted = true;
                console.log('[Aria] Audio capture started');
            }}
        """)

        await status("Audio capture active")

        # Poll audio chunks and forward to pipeline
        while True:
            chunks = await page.evaluate("""
                () => {
                    const chunks = window._audioChunks || [];
                    window._audioChunks = [];
                    return chunks;
                }
            """)
            for chunk in chunks:
                pcm_bytes = struct.pack(f"{len(chunk)}h", *chunk)
                await audio_callback(pcm_bytes)

            await asyncio.sleep(0.05)
