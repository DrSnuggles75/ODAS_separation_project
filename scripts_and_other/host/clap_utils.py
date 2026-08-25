#!/usr/bin/env python3
"""Minimal audio loader shared by classify_capture.py and sound_similarity.py.

Extracted from the project's offline_CLAP.py so the two analysis scripts don't drag in
its heavy imports (pandas / tqdm / sounddevice / transformers at module load). Needs only
soundfile + scipy + numpy.
"""
import numpy as np
import soundfile as sf
from scipy import signal


def load_audio_file(path, target_sr, play=False) -> np.ndarray:
    """Read a WAV, downmix to mono, resample to target_sr, return float32."""
    audio_file, org_sr = sf.read(path, always_2d=True)
    mono_audio = np.mean(audio_file, axis=1)
    if org_sr != target_sr:
        target_length = int(len(mono_audio) * target_sr / org_sr)
        mono_audio = signal.resample(mono_audio, target_length)
    return mono_audio.astype(np.float32)
