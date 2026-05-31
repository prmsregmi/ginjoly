import asyncio
import base64
import re
import shutil
import struct
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

WORKLET_JS = (Path(__file__).parent.parent / "static" / "audio_worklet.js").read_text()
MIC_INJECT_JS = (Path(__file__).parent.parent / "static" / "mic_inject.js").read_text()


async def _playback_pump(page, queue: asyncio.Queue):
    """Drain TTS PCM from the pipeline and feed it into the page's injected mic.

    Coalesces whatever is already queued into one feed call to cut page.evaluate
    round-trips, then base64-encodes it for the JSON-only evaluate boundary.
    """
    while True:
        chunk = await queue.get()
        buf = bytearray(chunk)
        try:
            while True:
                buf += queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        b64 = base64.b64encode(bytes(buf)).decode()
        try:
            await page.evaluate("(b64) => window.__feedPCM && window.__feedPCM(b64)", b64)
        except Exception:
            pass


async def join_meet(
    meeting_url: str,
    audio_callback,
    status_callback=None,
    bot_name: str = "Carleton",
    playback_queue: asyncio.Queue | None = None,
    playback_sample_rate: int = 48000,
):
    """
    Joins a Google Meet as a guest bot.
    Calls audio_callback(pcm_bytes) with raw 16kHz mono int16 PCM.
    Calls status_callback(str) with status updates.
    When playback_queue is given, the bot speaks the TTS PCM on it into the Meet.
    """

    async def status(msg: str):
        print(f"[meet_bot] {msg}")
        if status_callback:
            await status_callback(msg)

    # Fresh throwaway profile per launch. A shared user_data_dir stays locked
    # while a previous bot is still in a meeting, so re-joining the same call
    # fails with "Opening in existing browser session"; a unique dir avoids it.
    # Created outside the playwright context so it's removed only after Chrome
    # has fully stopped (closing the context first), otherwise the rmtree races
    # the live browser and silently leaks the directory.
    profile_dir = tempfile.mkdtemp(prefix="aria-chrome-")
    try:
        async with async_playwright() as pw:
            # Use real Chrome to avoid bot detection
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="chrome",
                headless=False,
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
                permissions=["microphone", "camera"],
            )
            try:
                # Replace the bot's mic with a Web Audio stream we feed TTS into,
                # before any page script runs, so Meet picks up the fake mic.
                await context.add_init_script(
                    MIC_INJECT_JS.replace("__SAMPLE_RATE__", str(playback_sample_rate))
                )

                page = await context.new_page()
                await status("Navigating to meeting...")
                await page.goto(meeting_url)
                await page.wait_for_timeout(3000)

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
                    name_input = page.locator(
                        "input[placeholder*='name' i], input[aria-label*='name' i]"
                    ).first
                    await name_input.wait_for(state="visible", timeout=5000)
                    await name_input.fill(bot_name)
                    await page.wait_for_timeout(500)
                except Exception:
                    pass

                # Join with the camera off but the mic LIVE: the bot speaks via the
                # injected mic, so it stays unmuted and sends silence when idle.
                # The green-room toggle reads "Turn off camera" while it's on;
                # idempotent (skips if already off/absent).
                for label in ["Turn off camera"]:
                    try:
                        btn = page.get_by_role("button", name=re.compile(label, re.I)).first
                        if await btn.is_visible(timeout=2000):
                            await btn.click()
                            await page.wait_for_timeout(300)
                    except Exception:
                        pass

                # Click "Ask to join" (guest join goes to waiting room)
                for text in ["Ask to join", "Join now", "Join"]:
                    try:
                        btn = page.get_by_role("button", name=text)
                        if await btn.is_visible(timeout=3000):
                            await btn.click()
                            await status(f"Waiting to be admitted as '{bot_name}'...")
                            break
                    except Exception:
                        pass

                # Wait until actually inside the meeting (mic button appears)
                try:
                    await page.locator(
                        "[data-is-muted], [aria-label*='microphone' i], [aria-label*='mic' i]"
                    ).first.wait_for(
                        state="visible",
                        timeout=120000,  # host has 2 min to admit
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

                        // Meet plays remote participants through media elements whose
                        // audio is a live WebRTC MediaStream on `srcObject`.
                        // createMediaElementSource outputs silence for those, so tap the
                        // stream directly with createMediaStreamSource (and don't route
                        // it to ctx.destination — the element still plays on its own).
                        const hookElement = (el) => {{
                            try {{
                                if (el._ariaHooked) return;
                                const stream = el.srcObject || (el.captureStream && el.captureStream());
                                if (!stream || !stream.getAudioTracks || stream.getAudioTracks().length === 0) return;
                                el._ariaHooked = true;
                                ctx.createMediaStreamSource(stream).connect(dest);
                            }} catch(e) {{}}
                        }};

                        const scan = () => document.querySelectorAll('audio, video').forEach(hookElement);
                        scan();

                        // Meet attaches/swaps streams after the elements exist, and
                        // srcObject is a property (invisible to MutationObserver), so
                        // re-scan on DOM changes and on a short interval.
                        new MutationObserver(scan).observe(document.body, {{ childList: true, subtree: true }});
                        setInterval(scan, 1000);

                        const workletBlob = new Blob(
                            [atob('{worklet_b64}')],
                            {{ type: 'application/javascript' }}
                        );
                        await ctx.audioWorklet.addModule(URL.createObjectURL(workletBlob));

                        const workletNode = new AudioWorkletNode(ctx, 'audio-capture-processor');
                        ctx.createMediaStreamSource(dest.stream).connect(workletNode);

                        workletNode.port.onmessage = (e) => {{
                            window._audioChunks = window._audioChunks || [];
                            window._audioChunks.push(Array.from(new Int16Array(e.data)));
                        }};

                        window._audioCaptureStarted = true;
                        console.log('[{bot_name}] Audio capture started');
                    }}
                """)

                await status("Audio capture active")

                # Resume the injected mic's AudioContext (autoplay-gated in
                # automated Chromium; a synthetic body click satisfies the gesture).
                try:
                    await page.evaluate(
                        "() => { try { document.body && document.body.click(); } catch (e) {} "
                        "return window.__botResume && window.__botResume(); }"
                    )
                except Exception:
                    pass

                # Speak the bot's TTS into the meeting via the injected mic.
                pump_task = (
                    asyncio.create_task(_playback_pump(page, playback_queue))
                    if playback_queue is not None
                    else None
                )

                # Poll audio chunks and forward to pipeline
                try:
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
                finally:
                    if pump_task:
                        pump_task.cancel()
            finally:
                # Close the browser before deleting the profile dir; rmtree while
                # Chrome is still running leaks a zombie process.
                try:
                    await context.close()
                except Exception:
                    pass
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)
