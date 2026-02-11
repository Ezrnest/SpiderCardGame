import math
import random
import struct
import subprocess
import sys
import wave
from pathlib import Path
from shutil import which
from time import time


class SoundFxManager:
    def __init__(self):
        self.enabled = True
        self.asset_dir = Path(__file__).with_name("assets").joinpath("sfx")
        self.real_dir = self.asset_dir / "real"
        # Reserved real-sample paths. Put your recorded wav files here.
        self.real_paths = {
            "move": self.real_dir / "move_card_real.wav",
            "deal": self.real_dir / "deal_card_real.wav",
            "collect": self.real_dir / "collect_stack_real.wav",
            "victory": self.real_dir / "victory_ode_to_joy_real.wav",
        }
        self.paths = {
            "move": self.asset_dir / "move_card.wav",
            "deal": self.asset_dir / "deal_card.wav",
            "collect": self.asset_dir / "collect_stack.wav",
            "victory": self.asset_dir / "victory_ode_to_joy.wav",
        }
        self.last_play = {"move": 0.0, "deal": 0.0, "collect": 0.0, "victory": 0.0}
        self.min_interval = {"move": 0.04, "deal": 0.06, "collect": 0.08, "victory": 0.5}
        self._linux_player = which("paplay") or which("aplay")
        self._ensure_assets()

    def play_move(self):
        self._play("move")

    def play_collect(self):
        self._play("collect")

    def play_deal(self):
        self._play("deal")

    def play_victory(self):
        self._play("victory")

    def _play(self, key: str):
        if not self.enabled:
            return
        path = self._resolve_path(key)
        if path is None or not path.exists():
            return
        now = time()
        if now - self.last_play.get(key, 0.0) < self.min_interval.get(key, 0.0):
            return
        self.last_play[key] = now

        try:
            if sys.platform == "win32":
                import winsound

                winsound.PlaySound(str(path), winsound.SND_ASYNC | winsound.SND_FILENAME | winsound.SND_NODEFAULT)
                return
            if sys.platform == "darwin":
                if which("afplay"):
                    subprocess.Popen(["afplay", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            if self._linux_player:
                subprocess.Popen([self._linux_player, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            # Never break gameplay for audio failures.
            return

    def _resolve_path(self, key: str):
        real = self.real_paths.get(key)
        if real is not None and real.exists():
            return real
        return self.paths.get(key)

    def _ensure_assets(self):
        try:
            self.asset_dir.mkdir(parents=True, exist_ok=True)
            self.real_dir.mkdir(parents=True, exist_ok=True)
            # Always regenerate: keeps tone updates effective across app restarts.
            self._write_move_card(self.paths["move"])
            self._write_deal_card(self.paths["deal"])
            self._write_collect_stack(self.paths["collect"])
            self._write_victory_ode_to_joy(self.paths["victory"])
        except Exception:
            self.enabled = False

    @staticmethod
    def _write_wav(path: Path, samples, sample_rate=22050):
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            frames = b"".join(struct.pack("<h", max(-32767, min(32767, int(s * 32767)))) for s in samples)
            wf.writeframes(frames)

    @staticmethod
    def _write_move_card(path: Path):
        sr = 22050
        duration = 0.07
        total = int(sr * duration)
        samples = []
        rng = random.Random(7)
        for i in range(total):
            t = i / sr
            # Softer "paper/wood" contact: low-mid tone + tiny noise.
            f = 220.0 + 40.0 * (1.0 - t / duration)
            env = math.exp(-28.0 * t)
            tone = math.sin(2.0 * math.pi * f * t) * 0.65
            tone += math.sin(2.0 * math.pi * (f * 2.1) * t) * 0.18
            noise = (rng.random() * 2.0 - 1.0) * 0.10
            sample = (tone + noise) * env * 0.70
            samples.append(sample)
        SoundFxManager._write_wav(path, samples, sample_rate=sr)

    @staticmethod
    def _write_deal_card(path: Path):
        sr = 22050
        duration = 0.09
        total = int(sr * duration)
        samples = []
        rng = random.Random(11)
        for i in range(total):
            t = i / sr
            f = 260.0 + 90.0 * (t / duration)
            env = math.exp(-22.0 * t)
            tone = math.sin(2.0 * math.pi * f * t) * 0.55
            tone += math.sin(2.0 * math.pi * (f * 1.9) * t) * 0.22
            noise = (rng.random() * 2.0 - 1.0) * 0.08
            sample = (tone + noise) * env * 0.62
            samples.append(sample)
        SoundFxManager._write_wav(path, samples, sample_rate=sr)

    @staticmethod
    def _write_collect_stack(path: Path):
        sr = 22050
        duration = 0.14
        total = int(sr * duration)
        samples = []
        rng = random.Random(19)
        for i in range(total):
            t = i / sr
            # Brush-like but still natural: filtered noise + gentle rise.
            f = 300.0 + 420.0 * (t / duration)
            env = math.exp(-10.0 * t)
            tone = math.sin(2.0 * math.pi * f * t) * 0.42
            tone += math.sin(2.0 * math.pi * (f * 1.5) * t) * 0.20
            noise = (rng.random() * 2.0 - 1.0) * 0.12
            sample = (tone + noise) * env * 0.65
            samples.append(sample)
        SoundFxManager._write_wav(path, samples, sample_rate=sr)

    @staticmethod
    def _write_victory_ode_to_joy(path: Path):
        sr = 22050
        # Beethoven "Ode to Joy" opening phrase in C major.
        notes = [
            (329.63, 0.24),  # E
            (329.63, 0.24),  # E
            (349.23, 0.24),  # F
            (392.00, 0.24),  # G
            (392.00, 0.24),  # G
            (349.23, 0.24),  # F
            (329.63, 0.24),  # E
            (293.66, 0.24),  # D
            (261.63, 0.26),  # C
            (261.63, 0.26),  # C
            (293.66, 0.24),  # D
            (329.63, 0.24),  # E
            (329.63, 0.34),  # E
            (293.66, 0.22),  # D
            (293.66, 0.40),  # D
        ]
        samples = []
        elapsed = 0.0
        for freq, dur in notes:
            total = int(sr * dur)
            for i in range(total):
                t = i / sr
                env = min(1.0, t * 16.0) * math.exp(-3.2 * t)
                s1 = math.sin(2.0 * math.pi * freq * (elapsed + t))
                s2 = math.sin(2.0 * math.pi * (freq * 2.0) * (elapsed + t)) * 0.22
                s3 = math.sin(2.0 * math.pi * (freq * 0.5) * (elapsed + t)) * 0.10
                samples.append((s1 + s2 + s3) * env * 0.38)
            # Short gap between notes.
            gap = int(sr * 0.015)
            samples.extend([0.0] * gap)
            elapsed += dur + 0.015
        SoundFxManager._write_wav(path, samples, sample_rate=sr)
