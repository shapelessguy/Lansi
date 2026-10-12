// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

const ENDPOINT = "https://openrouter.ai/api/v1/audio/speech";

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

export interface SpeechModel {
    id: string;
    voices: string[];
}

/** The speech models OpenRouter offers, with the voices each one has. Needs no key. */
export async function fetchSpeechModels(): Promise<SpeechModel[]> {
    const response = await fetch("https://openrouter.ai/api/v1/models?output_modalities=speech");
    const models: { id: string; supported_voices?: string[] }[] = (await response.json()).data;
    return models.map((model) => ({ id: model.id, voices: model.supported_voices ?? [] }));
}

async function errorMessage(response: Response): Promise<string> {
    const body = await response.text();
    try {
        return JSON.parse(body).error.message;
    } catch {
        return body || `OpenRouter speech request failed (${response.status})`;
    }
}

export interface Speech {
    /** A WAV or MP3 file. */
    audio: Blob;
    /** OpenRouter's id for the request, with which its cost can be looked up. */
    generationId: string | null;
}

/** Has a speech model read `input` aloud. */
export async function synthesizeSpeech(options: {
    apiKey: string;
    model: string;
    voice: string;
    input: string;
    /** How to read it, such as "slowly and clearly". Not spoken. */
    instructions: string;
    signal: AbortSignal;
}): Promise<Speech> {
    const response = await fetch(ENDPOINT, {
        method: "POST",
        headers: {
            Authorization: `Bearer ${options.apiKey}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            model: options.model,
            input: options.input,
            voice: options.voice,
            response_format: "pcm",
            ...(options.instructions.trim() ? { instructions: options.instructions.trim() } : {}),
        }),
        signal: options.signal,
    });
    if (!response.ok) {
        throw new Error(await errorMessage(response));
    }
    const data = await response.arrayBuffer();
    if (data.byteLength === 0) {
        throw new Error("The speech model returned no audio.");
    }
    return {
        audio: playableAudio(data, response.headers.get("Content-Type") ?? ""),
        generationId: response.headers.get("X-Generation-Id"),
    };
}
