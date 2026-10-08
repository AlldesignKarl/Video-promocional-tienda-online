"""Banda sonora original del anuncio (sintetizada desde cero, sin derechos de terceros).

Ritmo: 1 pulso = 0,55 s (109 BPM) y cada compás de 4 pulsos dura 2,2 s, igual que el montaje:
cada toque de color en la tienda cae en un pulso y suena una nota de una melodía que sube.

Uso: python3 tools/music.py build/audio/musica.f32   (float32 estéreo intercalado, 48 kHz)
"""
import sys
import numpy as np

try:
    from scipy.signal import lfilter
except ImportError:  # sin scipy funciona igual, solo más lento
    lfilter = None

SR = 48000
DUR = 19.8
BEAT = 0.55
N = int(SR * (DUR + 0.2))
rng = np.random.default_rng(1008)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def t_axis(n):
    return np.arange(n) / SR


def place(buf, sig, t0, gain=1.0, pan=0.0):
    """Suma una señal mono o estéreo en el instante t0 (s) con panorama -1..1."""
    i = int(round(t0 * SR))
    if sig.ndim == 1:
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        sig = np.stack([sig * l * 1.4142, sig * r * 1.4142], 1)
    if i < 0:
        sig, i = sig[-i:], 0
    j = min(len(buf), i + len(sig))
    if j > i:
        buf[i:j] += sig[: j - i] * gain


def env_adsr(n, a, d, s, r, hold):
    t = t_axis(n)
    e = np.where(t < a, t / max(a, 1e-4), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    rel = np.clip((t - hold) / max(r, 1e-4), 0, 1)
    return e * (1 - rel) ** 2


def onepole_lp(x, fc):
    """Paso bajo de un polo (fc puede variar en el tiempo)."""
    if np.isscalar(fc) and lfilter is not None:
        a = np.exp(-2 * np.pi * fc / SR)
        return lfilter([1 - a], [1, -a], x, axis=0)
    fc = np.broadcast_to(np.asarray(fc, dtype=float), x.shape[:1])
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x)
    z = np.zeros(x.shape[1:]) if x.ndim > 1 else 0.0
    for i in range(len(x)):
        z = (1 - a[i]) * x[i] + a[i] * z
        y[i] = z
    return y


def stft_filter(x, gain_fn, nfft=2048, hop=512):
    """Filtra ruido con una ganancia que depende del tiempo y la frecuencia (para barridos)."""
    win = np.hanning(nfft)
    out = np.zeros(len(x) + nfft)
    norm = np.zeros(len(x) + nfft)
    freqs = np.fft.rfftfreq(nfft, 1 / SR)
    for start in range(0, len(x) - 1, hop):
        seg = x[start:start + nfft]
        if len(seg) < nfft:
            seg = np.pad(seg, (0, nfft - len(seg)))
        spec = np.fft.rfft(seg * win) * gain_fn((start + nfft / 2) / SR, freqs)
        out[start:start + nfft] += np.fft.irfft(spec) * win
        norm[start:start + nfft] += win ** 2
    return (out / np.maximum(norm, 1e-3))[: len(x)]


# ---------------------------------------------------------------- instrumentos
def bell(f, dur=1.6, bright=1.0):
    """Campanita FM (celesta) para las notas de los colores."""
    n = int(dur * SR)
    t = t_axis(n)
    idx = (2.2 * bright) * np.exp(-t / 0.18) + 0.25
    mod = np.sin(2 * np.pi * f * 3.5 * t) * idx
    car = np.sin(2 * np.pi * f * t + mod)
    car += 0.35 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t / 0.25)
    e = (1 - np.exp(-t / 0.002)) * np.exp(-t / 0.55)
    return car * e


def epiano(f, dur=0.9, vel=1.0):
    n = int(dur * SR)
    t = t_axis(n)
    idx = 1.6 * vel * np.exp(-t / 0.12) + 0.35
    car = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
    car += 0.2 * np.sin(2 * np.pi * f * 4.0 * t) * np.exp(-t / 0.05) * vel
    e = (1 - np.exp(-t / 0.003)) * np.exp(-t / 0.42)
    return car * e * vel


def pad(notes, t0, t1, bright, attack=0.5, release=0.9):
    """Colchón de cuerdas sintéticas: dientes de sierra desafinados con filtro que varía."""
    n = int((t1 - t0 + release) * SR)
    t = t_axis(n)
    out = np.zeros((n, 2))
    fc = bright(t + t0) if callable(bright) else np.full(n, bright)
    e = env_adsr(n, attack, 1.0, 1.0, release, t1 - t0)
    for m in notes:
        f0 = mtof(m)
        for det, pan in ((-0.09, -0.7), (0.0, 0.0), (0.085, 0.7)):
            f = f0 * 2 ** (det / 12)
            ph = rng.random() * 6.28
            sig = np.zeros(n)
            for k in range(1, 40):
                if k * f > 9000:
                    break
                amp = (1 / k) / np.sqrt(1 + (k * f / fc) ** 4)
                sig += amp * np.sin(2 * np.pi * k * f * t + ph * k)
            l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
            out[:, 0] += sig * l
            out[:, 1] += sig * r
    return out * e[:, None] / (len(notes) * 2.2)


def bass(f, dur, vel=1.0):
    n = int(dur * SR)
    t = t_axis(n)
    sig = np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * 2 * f * t) + 0.18 * np.sin(2 * np.pi * 3 * f * t)
    e = (1 - np.exp(-t / 0.004)) * np.exp(-t / 0.9) * np.clip((dur - t) / 0.05, 0, 1)
    return np.tanh(sig * 1.3) * e * vel


def kick(vel=1.0):
    n = int(0.5 * SR)
    t = t_axis(n)
    f = 52 + 120 * np.exp(-t / 0.03)
    ph = 2 * np.pi * np.cumsum(f) / SR
    sig = np.sin(ph) * np.exp(-t / 0.24)
    click = rng.standard_normal(n) * np.exp(-t / 0.002) * 0.25
    return np.tanh((sig + click) * 1.5) * vel


def snap(vel=1.0):
    n = int(0.35 * SR)
    t = t_axis(n)
    noise = rng.standard_normal(n)
    bp = onepole_lp(noise, 4200) - onepole_lp(noise, 900)
    e = np.zeros(n)
    for d in (0.0, 0.011, 0.022):
        e += np.where(t >= d, np.exp(-(t - d) / (0.012 if d < 0.02 else 0.11)), 0)
    return bp * e * 2.2 * vel


def hat(vel=1.0, dec=0.035):
    n = int(0.2 * SR)
    t = t_axis(n)
    noise = rng.standard_normal(n)
    hp = noise - onepole_lp(noise, 7000)
    return hp * np.exp(-t / dec) * vel


def tick(f=2200, vel=1.0):
    n = int(0.08 * SR)
    t = t_axis(n)
    return (np.sin(2 * np.pi * f * t) * np.exp(-t / 0.012) + 0.3 * rng.standard_normal(n) * np.exp(-t / 0.003)) * vel


def whoosh(dur, f0, f1, peak=0.6, width=0.6):
    """Ráfaga de aire con un filtro de banda que barre de f0 a f1."""
    n = int(dur * SR)
    noise = rng.standard_normal(n)

    def g(tt, fr):
        x = np.clip(tt / dur, 0, 1)
        fc = f0 * (f1 / f0) ** x
        return np.exp(-0.5 * (np.log2(np.maximum(fr, 20) / fc) / width) ** 2)

    sig = stft_filter(noise, g)
    t = t_axis(n)
    x = t / dur
    e = np.where(x < peak, (x / peak) ** 2, np.exp(-(x - peak) / (1 - peak) * 4))
    pan = np.sin(np.pi * (x - 0.5)) * 0.8
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    return np.stack([sig * e * l, sig * e * r], 1) * 1.4


def boom(dur=2.4, vel=1.0):
    n = int(dur * SR)
    t = t_axis(n)
    f = 34 + 60 * np.exp(-t / 0.08)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.55)
    noise = rng.standard_normal(n)
    thump = onepole_lp(noise, 300) * np.exp(-t / 0.18) * 3
    air = (noise - onepole_lp(noise, 3000)) * np.exp(-t / 0.5) * 0.25
    return np.tanh((sub * 1.2 + thump + air) * 1.2) * vel


def riser(dur):
    n = int(dur * SR)
    t = t_axis(n)
    x = t / dur
    noise = rng.standard_normal(n)
    sig = stft_filter(noise, lambda tt, fr: np.exp(-0.5 * (np.log2(np.maximum(fr, 20) / (400 * 20 ** np.clip(tt / dur, 0, 1))) / 0.9) ** 2))
    tone = np.sin(2 * np.pi * np.cumsum(220 * 4 ** x) / SR) * 0.25
    return (sig * 0.9 + tone) * x ** 2.2


def reverb_ir(seconds=2.6, predelay=0.02):
    n = int(seconds * SR)
    t = t_axis(n)
    ir = np.zeros((n, 2))
    for c in range(2):
        noise = rng.standard_normal(n)
        # más oscuro cuanto más tarde (como una sala real)
        dark = onepole_lp(noise, 2500)
        bright_mix = np.exp(-t / 0.35)
        ir[:, c] = (noise * bright_mix + dark * (1 - bright_mix) * 1.6) * np.exp(-t / (seconds / 6.2))
    ir[: int(predelay * SR)] = 0
    return ir / np.sqrt((ir ** 2).sum(0, keepdims=True)) * 0.9


def convolve(x, ir):
    n = len(x) + len(ir)
    size = 1 << (n - 1).bit_length()
    out = np.zeros((len(x), 2))
    for c in range(2):
        X = np.fft.rfft(x[:, c], size)
        H = np.fft.rfft(ir[:, c], size)
        out[:, c] = np.fft.irfft(X * H, size)[: len(x)]
    return out


# ---------------------------------------------------------------- partitura
def compose():
    dry = np.zeros((N, 2))      # batería y efectos secos
    send = np.zeros((N, 2))     # lo que pasa por la reverb
    pads = np.zeros((N, 2))
    bassb = np.zeros((N, 2))
    kicks = []

    b = lambda k: k * BEAT  # instante del pulso k
    # acordes por compás (2,2 s): voicing del colchón, bajo, notas del arpegio
    CH = [
        ([50, 57, 61, 64, 66], 38, [62, 66, 69, 73, 76]),   # Dmaj9
        ([47, 54, 57, 61, 62], 35, [59, 62, 66, 69, 73]),   # Bm9
        ([43, 50, 54, 57, 59], 43, [59, 62, 66, 67, 71]),   # Gmaj9
        ([42, 50, 57, 61, 64], 42, [61, 64, 66, 69, 73]),   # D/F#
        ([45, 52, 54, 59, 62], 45, [59, 62, 64, 66, 69]),   # A6sus
        ([47, 54, 57, 61, 62], 35, [59, 62, 66, 69, 73]),   # Bm9
        ([43, 50, 54, 59, 61], 43, [61, 62, 66, 67, 71]),   # Gmaj7#11 (noche)
        ([50, 57, 61, 64, 66], 38, [62, 66, 69, 73, 76]),   # Dmaj9 (cierre)
        ([43, 50, 54, 57, 62], 43, [62, 66, 69, 71, 74]),   # Gadd9 → D
    ]

    # --- colchón ---
    def bright_curve(tt):
        # se abre al empezar, baja al caer la noche y se abre del todo al encenderse
        fc = 900 + 2600 * np.clip(tt / 2.2, 0, 1)
        fc = np.where(tt > 13.0, fc * np.clip(1 - (tt - 13.0) / 0.5, 0.12, 1), fc)
        fc = np.where(tt > 13.75, 3800 + 2500 * np.exp(-(tt - 13.75) / 0.8), fc)
        fc = np.where(tt > 14.85, 4200, fc)
        return fc

    for i, (v, _, _) in enumerate(CH):
        t0 = i * 2.2
        t1 = min(DUR, t0 + 2.2) if i < 8 else DUR - 0.6
        p = pad(v, t0, t1, bright_curve, attack=0.9 if i == 0 else 0.25, release=1.4 if i == 8 else 0.6)
        place(pads, p, t0, gain=0.55 if i else 0.5)
    # acorde final que se queda sonando
    place(pads, pad([50, 57, 61, 64, 66, 69], 17.6, DUR - 0.3, 3200, attack=0.3, release=1.6), 17.6, gain=0.5)

    # --- intro: arpegio de campanitas mientras aparece la portada de la tienda ---
    intro = [74, 78, 81, 85, 81, 78, 76, 73]
    for k, m in enumerate(intro):
        place(send, bell(mtof(m), 1.8, 0.7), 0.25 + k * BEAT / 2, gain=0.16 * (0.6 + 0.4 * k / 7), pan=(-0.5 + k / 7))
    # aire que sube hasta que el móvil se aleja
    place(send, whoosh(1.4, 250, 3500, 0.75, 0.8), 1.2, gain=0.14)
    place(dry, whoosh(0.9, 2500, 400, 0.35, 0.9), 2.15, gain=0.2)

    # --- batería: entra en el compás 2 (2,2 s) y para al caer la noche ---
    def groove(t_from, t_to, half=False):
        k0 = int(round(t_from / BEAT))
        k1 = int(round(t_to / BEAT))
        for k in range(k0, k1):
            tb = b(k)
            beat_in_bar = k % 4
            if not half or beat_in_bar in (0,):
                if beat_in_bar in (0, 2) or (not half and beat_in_bar == 3 and k % 8 == 7):
                    place(dry, kick(0.95 if beat_in_bar == 0 else 0.8), tb, gain=0.62)
                    kicks.append(tb)
            if (beat_in_bar in (1, 3) and not half) or (half and beat_in_bar == 2):
                place(send, snap(0.8), tb, gain=0.38, pan=0.05)
                place(dry, snap(0.8), tb, gain=0.32)
            # charles a corcheas en contratiempo y semicorcheas suaves
            place(dry, hat(0.5), tb + BEAT / 2, gain=0.16, pan=0.35)
            for s in (0.25, 0.75):
                place(dry, hat(0.25, 0.02), tb + BEAT * s, gain=0.09, pan=-0.3)

    groove(2.2, 13.2)
    groove(15.4, 17.6, half=True)

    # --- bajo ---
    for i, (_, root, _) in enumerate(CH):
        if i == 0:
            continue
        t0 = i * 2.2
        if 13.2 <= t0 < 14.85:   # noche: solo una nota larga y grave
            place(bassb, bass(mtof(root), 1.5, 0.7), t0, gain=0.5)
            continue
        if t0 >= 17.6:
            place(bassb, bass(mtof(38), 2.0, 0.8), 17.6, gain=0.55)
            continue
        pattern = [(0, 1.5), (1.5, 0.5), (2.5, 0.5), (3, 0.9)] if t0 < 13 else [(0, 1.8), (2, 1.8)]
        for off, ln in pattern:
            place(bassb, bass(mtof(root + (12 if off == 2.5 else 0)), ln * BEAT, 0.85), t0 + off * BEAT, gain=0.55)
    place(bassb, bass(mtof(38), 1.2, 0.9), 14.85, gain=0.6)

    # --- arpegio de piano eléctrico en corcheas (compases 2 a 6) ---
    for i in range(1, 6):
        _, _, arp = CH[i]
        seq = [arp[0], arp[2], arp[4], arp[2], arp[1], arp[3], arp[4], arp[3]]
        for s, m in enumerate(seq):
            tt = i * 2.2 + s * BEAT / 2
            if 6.9 < tt < 10.2:   # deja sitio a las notas de los colores
                vel = 0.45
            else:
                vel = 0.7 + 0.2 * (s % 2 == 0)
            place(send, epiano(mtof(m), 0.8, vel), tt, gain=0.12, pan=(-0.35 if s % 2 else 0.35))
    for s, m in enumerate([62, 66, 69, 73, 76, 73, 69, 66]):
        place(send, epiano(mtof(m), 0.9, 0.6), 15.4 + s * BEAT / 2, gain=0.1, pan=(-0.3 if s % 2 else 0.3))

    # --- toques en la tienda ---
    place(dry, tick(1900, 0.8), 5.85, gain=0.22)                       # pulsa la letra de resina
    place(send, whoosh(0.7, 300, 2400, 0.5, 0.8), 5.85, gain=0.1)      # se abre la ficha
    melody = [69, 73, 76, 78, 81, 83]                                  # una nota por color, subiendo
    for k, m in enumerate(melody):
        tt = 7.15 + k * BEAT
        place(dry, tick(2400, 0.7), tt - 0.005, gain=0.12)
        place(send, bell(mtof(m), 1.8, 1.0), tt, gain=0.42, pan=(-0.25 + 0.1 * k))
        place(send, bell(mtof(m + 12), 1.2, 0.5), tt + 0.002, gain=0.08)
    place(send, whoosh(0.5, 600, 1800, 0.5, 0.7), 10.2, gain=0.07)     # baja hasta la inicial
    place(dry, tick(1600, 0.9), 10.85, gain=0.25)                      # escribe la "A"
    place(send, bell(mtof(86), 1.4, 0.6), 10.85, gain=0.12)
    place(dry, tick(2000, 1.0), 11.35, gain=0.25)                      # Añadir a la cesta
    for m, d in ((86, 0.0), (93, 0.09)):
        place(send, bell(mtof(m), 1.6, 0.9), 11.35 + d, gain=0.3)

    # --- 100 combinaciones: un destello por imagen y el contador ---
    place(send, whoosh(0.6, 500, 5000, 0.45, 0.7), 11.2, gain=0.22)
    for k, tt in enumerate([11.825, 12.1, 12.375, 12.65, 12.925]):
        place(send, bell(mtof([78, 81, 83, 85, 88][k]), 1.0, 0.8), tt, gain=0.16, pan=(-0.4 + 0.2 * k))
        place(dry, hat(0.8, 0.05), tt, gain=0.12)
    for k in range(11):
        tt = 11.62 + (1 - (1 - k / 10) ** (1 / 3)) * 1.33
        place(dry, tick(3200 + 60 * k, 0.5), tt, gain=0.06, pan=0.2)

    # --- cae la noche: subida y encendido ---
    place(send, riser(0.75), 13.0, gain=0.38)
    place(dry, whoosh(0.9, 3000, 200, 0.3, 0.9), 12.95, gain=0.18)
    place(dry, boom(2.6, 1.0), 13.75, gain=0.55)
    place(send, boom(2.6, 1.0), 13.75, gain=0.25)
    sp = np.random.default_rng(5)
    pent = [74, 76, 78, 81, 83, 86, 88, 90, 93, 95]
    for k in range(26):
        tt = 13.75 + sp.random() ** 1.6 * 1.0
        place(send, bell(mtof(pent[sp.integers(len(pent))]), 1.4, 0.9), tt, gain=0.08 * (1 - (tt - 13.75)), pan=sp.uniform(-0.8, 0.8))

    # --- cierre ---
    place(send, riser(0.45), 14.4, gain=0.25)
    place(dry, boom(2.8, 0.9), 14.85, gain=0.45)
    place(send, boom(2.8, 0.9), 14.85, gain=0.2)
    place(dry, kick(1.0), 14.85, gain=0.6)
    kicks.append(14.85)
    for m in (62, 69, 73, 76, 78):
        place(send, epiano(mtof(m), 2.0, 0.9), 14.86, gain=0.12)
    place(send, whoosh(0.5, 4000, 900, 0.4, 0.8), 15.8, gain=0.05)      # aparece la web
    for k in range(6):                                                  # se escribe la dirección
        place(dry, tick(2600, 0.6), 15.98 + k * 0.1, gain=0.05)
    for k, m in enumerate([74, 78, 81, 85, 88]):                        # aparecen las miniaturas
        place(send, bell(mtof(m), 1.4, 0.6), 16.5 + k * 0.08, gain=0.09, pan=(-0.6 + 0.3 * k))
    for m in (86, 90, 93):
        place(send, bell(mtof(m), 2.4, 0.5), 17.6, gain=0.1)

    # --- compresión lateral: el colchón y el bajo respiran con el bombo ---
    duck = np.ones(N)
    tt = t_axis(N)
    for kt in kicks:
        i = int(kt * SR)
        seg = tt[: int(0.45 * SR)]
        g = 1 - 0.45 * np.exp(-seg / 0.12)
        j = min(N, i + len(seg))
        duck[i:j] = np.minimum(duck[i:j], g[: j - i])
    pads *= duck[:, None]
    bassb *= duck[:, None]

    ir = reverb_ir(2.8)
    wet = convolve(send + pads * 0.55, ir)
    mixb = dry + send * 0.95 + pads * 0.8 + bassb * 0.7 + wet * 0.6
    # fuera el subgrave que en un móvil no se oye (dos etapas de paso alto a 45 Hz)
    mixb = mixb - onepole_lp(mixb, 45)
    mixb = mixb - onepole_lp(mixb, 45)
    # agudos algo más suaves (menos siseo de platos y ráfagas)
    mixb = mixb - 0.4 * (mixb - onepole_lp(mixb, 6500))
    # fundido final
    fade = np.clip((DUR + 0.1 - tt) / 1.6, 0, 1) ** 1.5
    mixb *= fade[:, None]
    mixb[: int(0.01 * SR)] *= np.linspace(0, 1, int(0.01 * SR))[:, None]
    # saturación suave como limitador
    peak = np.max(np.abs(mixb))
    mixb = np.tanh(mixb / peak * 1.6) / np.tanh(1.6) * 0.89
    return mixb[: int(DUR * SR)].astype(np.float32)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "build/audio/musica.f32"
    compose().tofile(out)
    print("música:", out, DUR, "s")
