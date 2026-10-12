// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { pcmToWav, playableAudio, sampleRate } from "./speech";

const oneSecondAt8k = new ArrayBuffer(16_000);

async function header(wav: Blob): Promise<DataView> {
    return new DataView(await wav.slice(0, 44).arrayBuffer());
}

function ascii(view: DataView, offset: number, length: number): string {
    return String.fromCharCode(...Array.from({ length }, (_, i) => view.getUint8(offset + i)));
}

test("the sample rate is read from the content type", () => {
    expect(sampleRate("audio/pcm;rate=16000")).toBe(16000);
    expect(sampleRate("audio/L16; codec=pcm; rate=44100")).toBe(44100);
});

test("the sample rate defaults to 24 kHz when the content type does not give one", () => {
    expect(sampleRate("audio/pcm")).toBe(24000);
    expect(sampleRate("")).toBe(24000);
});

test("a WAV file describes the samples as 16-bit mono at the given rate", async () => {
    const wav = pcmToWav(oneSecondAt8k, 8000);

    const view = await header(wav);
    expect(wav.type).toBe("audio/wav");
    expect(wav.size).toBe(44 + 16_000);
    expect(ascii(view, 0, 4) + ascii(view, 8, 4) + ascii(view, 12, 4) + ascii(view, 36, 4)).toBe("RIFFWAVEfmt data");
    expect(view.getUint32(4, true)).toBe(36 + 16_000);
    expect({
        format: view.getUint16(20, true),
        channels: view.getUint16(22, true),
        rate: view.getUint32(24, true),
        bytesPerSecond: view.getUint32(28, true),
        bitsPerSample: view.getUint16(34, true),
        dataBytes: view.getUint32(40, true),
    }).toEqual({ format: 1, channels: 1, rate: 8000, bytesPerSecond: 16_000, bitsPerSample: 16, dataBytes: 16_000 });
});

test("raw samples are wrapped as WAV using the rate in the content type", async () => {
    const audio = playableAudio(oneSecondAt8k, "audio/pcm;rate=8000");

    expect(audio.type).toBe("audio/wav");
    expect((await header(audio)).getUint32(24, true)).toBe(8000);
});

test("audio that is already MP3 or WAV is kept as it is", () => {
    const data = new ArrayBuffer(10);

    expect(playableAudio(data, "audio/mpeg")).toMatchObject({ type: "audio/mpeg", size: 10 });
    expect(playableAudio(data, "audio/wav")).toMatchObject({ type: "audio/wav", size: 10 });
});
