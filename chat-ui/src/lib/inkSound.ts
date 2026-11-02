// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { Pen } from "./ink";

/**
 * The sound of a pen on paper, made rather than recorded: noise, shaped as
 * each tool sounds, as loud as the pen moves fast and presses hard, and
 * silent while it rests.
 */

export type Tool = Pen | "eraser";

/**
 * How each tool sounds: the band of the noise it lets through, how narrow,
 * and how loud at its fastest. A pencil scratches high and rough, a pen
 * hisses softly, a fountain pen's nib sings a little, a felt highlighter
 * squeaks low, and an eraser rubs lower still.
 */
const SOUNDS: Record<Tool, { frequency: number; q: number; loudness: number }> = {
    pencil: { frequency: 2200, q: 0.9, loudness: 0.08 },
    pen: { frequency: 1400, q: 1.2, loudness: 0.035 },
    fountain: { frequency: 1800, q: 1.8, loudness: 0.03 },
    highlighter: { frequency: 900, q: 1.6, loudness: 0.04 },
    eraser: { frequency: 500, q: 0.9, loudness: 0.07 },
};

/** How fast the pen moves, in pixels of the screen a millisecond, when it sounds loudest. */
const LOUDEST_SPEED = 1.2;

/** How loud all the tools are, together. */
const VOLUME = 0.6;

/** How fast the pen moves, in pixels of the screen a millisecond, below which it makes no sound. */
const SILENT_SPEED = 0.08;

/** How quickly the sound follows the pen, in seconds. */
const FOLLOW = 0.025;

/** How long after it last moved the pen is taken to rest, in seconds. */
const STILL_AFTER = 0.06;

let audio: AudioContext | null = null;
let gain: GainNode | null = null;
let filter: BiquadFilterNode | null = null;
let tool: Tool = "pen";

/**
 * Fills `samples` with the noise a tip makes on paper: pink, as soft in the
 * highs as most of what is heard, and rough with the grain of the paper,
 * which comes and goes many times a second.
 */
function paperNoise(samples: Float32Array, sampleRate: number) {
    // pink noise, as Paul Kellet filters white noise into it
    let [b0, b1, b2, b3, b4, b5, b6] = [0, 0, 0, 0, 0, 0, 0];
    // the grain: how rough the paper is where the tip is, changing about every 4 ms
    const grainEvery = Math.round(sampleRate * 0.004);
    let grain = 1;
    let nextGrain = 1;
    for (let at = 0; at < samples.length; at++) {
        if (at % grainEvery === 0) {
            grain = nextGrain;
            nextGrain = 0.35 + Math.random() * 0.65;
        }
        const rough = grain + (nextGrain - grain) * ((at % grainEvery) / grainEvery);
        const white = Math.random() * 2 - 1;
        b0 = 0.99886 * b0 + white * 0.0555179;
        b1 = 0.99332 * b1 + white * 0.0750759;
        b2 = 0.969 * b2 + white * 0.153852;
        b3 = 0.8665 * b3 + white * 0.3104856;
        b4 = 0.55 * b4 + white * 0.5329522;
        b5 = -0.7616 * b5 - white * 0.016898;
        const pink = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.11;
        b6 = white * 0.115926;
        samples[at] = pink * rough;
    }
}

/** The sound made ready, which a browser allows only as the learner touches the page. */
function ready(): boolean {
    if (!audio) {
        const Audio = window.AudioContext
            ?? (window as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!Audio) {
            return false;
        }
        audio = new Audio();
        const noise = audio.createBuffer(1, audio.sampleRate * 2, audio.sampleRate);
        paperNoise(noise.getChannelData(0), audio.sampleRate);
        const source = audio.createBufferSource();
        source.buffer = noise;
        source.loop = true;
        filter = audio.createBiquadFilter();
        filter.type = "bandpass";
        // what is left of the highs, which made it shrill, taken out
        const soft = audio.createBiquadFilter();
        soft.type = "lowpass";
        soft.frequency.value = 4500;
        gain = audio.createGain();
        gain.gain.value = 0;
        source.connect(filter).connect(soft).connect(gain).connect(audio.destination);
        source.start();
    }
    if (audio.state === "suspended") {
        void audio.resume();
    }
    return true;
}

/** Starts the sound of `writing` with a tool, silent until it moves. */
export function startSound(writing: Tool) {
    if (!ready() || !audio || !filter) {
        return;
    }
    tool = writing;
    filter.frequency.setValueAtTime(SOUNDS[tool].frequency, audio.currentTime);
    filter.Q.setValueAtTime(SOUNDS[tool].q, audio.currentTime);
}

/** The pen moved at `speed`, in pixels of the screen a millisecond, pressing as hard as `pressure`, from 0 to 1. */
export function moveSound(speed: number, pressure: number) {
    if (!audio || !gain) {
        return;
    }
    // nothing below a slow pace, and from there louder ever more steeply
    const fast = Math.min(1, Math.max(0, (speed - SILENT_SPEED) / (LOUDEST_SPEED - SILENT_SPEED)));
    const loud = VOLUME * SOUNDS[tool].loudness * fast ** 1.5 * (0.5 + pressure);
    const now = audio.currentTime;
    // a pen sounds higher the faster it goes
    if (filter) {
        filter.frequency.setTargetAtTime(SOUNDS[tool].frequency * (0.75 + 0.5 * fast), now, FOLLOW * 2);
    }
    gain.gain.cancelScheduledValues(now);
    gain.gain.setTargetAtTime(loud, now, FOLLOW);
    // a pen that stops moving, while it still touches the page, falls silent unless it moves again
    gain.gain.setTargetAtTime(0, now + STILL_AFTER, FOLLOW);
}

/** The pen was lifted. */
export function stopSound() {
    if (!audio || !gain) {
        return;
    }
    gain.gain.setTargetAtTime(0, audio.currentTime, FOLLOW);
}
