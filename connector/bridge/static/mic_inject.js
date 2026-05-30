// Injected via context.add_init_script BEFORE Meet loads. Replaces the bot's
// microphone with a Web Audio stream we feed TTS PCM into, so the bot can speak
// into the meeting. The real mic is never used; getUserMedia hands Meet a track
// off a MediaStreamDestination that an AudioWorklet drives from injected PCM.
//
// __SAMPLE_RATE__ is substituted by the Python side; it must match the rate the
// pipeline emits TTS at (audio_out_sample_rate) so playback isn't pitch-shifted.
(() => {
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;

  const SAMPLE_RATE = __SAMPLE_RATE__;
  let ctx = null;
  let dest = null;
  let node = null;
  let setupPromise = null;

  // Pulls injected Float32 chunks off a queue and emits them sample-by-sample;
  // outputs silence on underflow so an empty queue is a gap, not a glitch.
  const WORKLET_SRC = `
    class PCMPlayback extends AudioWorkletProcessor {
      constructor() {
        super();
        this._q = [];
        this._off = 0;
        this.port.onmessage = (e) => { this._q.push(e.data); };
      }
      process(_inputs, outputs) {
        const out = outputs[0][0];
        if (!out) return true;
        let i = 0;
        while (i < out.length) {
          if (this._q.length === 0) { out[i++] = 0; continue; }
          const cur = this._q[0];
          out[i++] = cur[this._off++];
          if (this._off >= cur.length) { this._q.shift(); this._off = 0; }
        }
        return true;
      }
    }
    registerProcessor('pcm-playback', PCMPlayback);
  `;

  function ensure() {
    if (setupPromise) return setupPromise;
    setupPromise = (async () => {
      ctx = new AC({ sampleRate: SAMPLE_RATE });
      dest = ctx.createMediaStreamDestination();
      const url = URL.createObjectURL(new Blob([WORKLET_SRC], { type: 'application/javascript' }));
      await ctx.audioWorklet.addModule(url);
      node = new AudioWorkletNode(ctx, 'pcm-playback');
      node.connect(dest);

      // Resume is gated behind a user gesture in automated Chromium; the Python
      // side calls this after admission (right after a synthetic body click).
      window.__botResume = () => ctx.resume().catch(() => {});

      // Called from Python with base64 int16 mono PCM at SAMPLE_RATE.
      window.__feedPCM = (b64) => {
        if (!node) return;
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const i16 = new Int16Array(bytes.buffer);
        const f32 = new Float32Array(i16.length);
        for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
        node.port.postMessage(f32, [f32.buffer]);
      };
    })();
    return setupPromise;
  }

  const orig = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async (constraints) => {
    if (!constraints || !constraints.audio) return orig(constraints);
    await ensure();
    const tracks = [...dest.stream.getAudioTracks()];
    // Pass any requested video through to the real device so the camera preview
    // still works (we disable it via the UI toggle, not by dropping the track).
    if (constraints.video) {
      try {
        const v = await orig({ video: constraints.video });
        for (const t of v.getVideoTracks()) tracks.push(t);
      } catch (e) {}
    }
    return new MediaStream(tracks);
  };
})();
