// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/** What Gemini's speech models produce when the reply does not say otherwise. */
const DEFAULT_SAMPLE_RATE = 24_000;

/** The sample rate named in a content type such as `audio/pcm;rate=24000`. */
export function sampleRate(contentType: string): number {
    const rate = /rate=(\d+)/.exec(contentType);
    return rate ? Number(rate[1]) : DEFAULT_SAMPLE_RATE;
}

/**
 * Puts a WAV header in front of raw 16-bit mono samples, so that browsers and
 * other players can open them.
 */
export function pcmToWav(pcm: ArrayBuffer, rate: number): Blob {
    const header = new DataView(new ArrayBuffer(44));
    const ascii = (offset: number, text: string) => {
        for (let i = 0; i < text.length; i++) {
            header.setUint8(offset + i, text.charCodeAt(i));
        }
    };
    const bytesPerSample = 2;
    ascii(0, "RIFF");
    header.setUint32(4, 36 + pcm.byteLength, true);
    ascii(8, "WAVE");
    ascii(12, "fmt ");
    header.setUint32(16, 16, true);
    // uncompressed, one channel
    header.setUint16(20, 1, true);
    header.setUint16(22, 1, true);
    header.setUint32(24, rate, true);
    header.setUint32(28, rate * bytesPerSample, true);
    header.setUint16(32, bytesPerSample, true);
    header.setUint16(34, 8 * bytesPerSample, true);
    ascii(36, "data");
    header.setUint32(40, pcm.byteLength, true);
    return new Blob([header, pcm], { type: "audio/wav" });
}

/** Turns what the speech endpoint returned into a file players can open. */
export function playableAudio(data: ArrayBuffer, contentType: string): Blob {
    const type = contentType.toLowerCase();
    if (type.includes("mpeg") || type.includes("mp3")) {
        return new Blob([data], { type: "audio/mpeg" });
    }
    if (type.includes("wav")) {
        return new Blob([data], { type: "audio/wav" });
    }
    return pcmToWav(data, sampleRate(type));
}
