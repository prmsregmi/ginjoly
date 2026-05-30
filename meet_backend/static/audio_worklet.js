// Injected into the Meet page. Captures all audio output and sends PCM over WebSocket.
class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
    this._bufferSize = 4096;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    // Mix down to mono
    const channel = input[0];
    for (let i = 0; i < channel.length; i++) {
      this._buffer.push(channel[i]);
    }

    if (this._buffer.length >= this._bufferSize) {
      const chunk = new Float32Array(this._buffer.splice(0, this._bufferSize));
      // Convert float32 to int16 PCM
      const pcm = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        pcm[i] = Math.max(-32768, Math.min(32767, chunk[i] * 32768));
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }

    return true;
  }
}

registerProcessor("audio-capture-processor", AudioCaptureProcessor);
