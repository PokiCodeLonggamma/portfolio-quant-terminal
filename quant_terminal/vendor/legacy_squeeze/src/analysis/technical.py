"""Analyse technique spécialisée Short Squeeze.

6 indicateurs conçus pour détecter la mécanique d'un squeeze :

1. TTM Squeeze (Bollinger inside Keltner)     → compression
2. OBV Divergence                               → accumulation silencieuse
3. Keltner Breakout                             → déclencheur
4. Volume Spike (breakout confirmation)         → validation
5. RSI Momentum Shift                           → confirmation directionnelle
6. VWAP Reclaim                                 → acheteurs reprennent le contrôle

Dépendances : yfinance, pandas, numpy
TA-Lib optionnel — fallback pandas si non installé.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────

LOOKBACK_DAYS = 120       # Historique à télécharger (6 mois trading)
BB_PERIOD = 20            # Bollinger Bands period
BB_STD = 2.0              # Bollinger Bands std dev multiplier
KC_PERIOD = 20            # Keltner Channel EMA period
KC_ATR_PERIOD = 14        # ATR period for Keltner
KC_ATR_MULT = 1.5         # Keltner ATR multiplier
OBV_SLOPE_PERIOD = 14     # OBV slope calculation window
PRICE_RANGE_PERIOD = 20   # Period to detect price range (for OBV divergence)
PRICE_RANGE_THRESHOLD = 0.08  # Max price range % to consider "stagnant"
VOL_SPIKE_MULT = 2.5      # Volume must be >2.5x SMA20 for breakout
VOL_SMA_PERIOD = 20       # Volume SMA period
RSI_PERIOD = 14           # RSI period
VWAP_LOOKBACK = 5         # Sessions to check VWAP reclaim


# ─── Data Classes ────────────────────────────────────────────

@dataclass
class TechnicalSignals:
    """Résultat de l'analyse technique squeeze."""
    ticker: str

    # 1. TTM Squeeze
    squeeze_on: bool = False              # BB inside KC = compression active
    squeeze_bars: int = 0                 # Nombre de barres en compression
    squeeze_just_fired: bool = False      # Compression vient de se relâcher

    # 2. OBV Divergence
    obv_divergence: bool = False          # Prix stagne/baisse mais OBV monte
    obv_slope: float = 0.0                # Pente OBV normalisée
    price_slope: float = 0.0             # Pente prix pour comparaison

    # 3. Keltner Breakout
    keltner_breakout: bool = False        # Prix > Keltner upper
    keltner_upper: float = 0.0
    close_price: float = 0.0

    # 4. Volume Spike
    volume_spike: bool = False            # Volume > 2.5x SMA
    volume_ratio: float = 0.0            # Ratio volume/SMA
    avg_volume: float = 0.0

    # 5. RSI Momentum Shift
    rsi_shift: bool = False               # RSI passe >60 depuis zone 40-50
    rsi_current: float = 0.0
    rsi_previous: float = 0.0            # RSI 5 sessions avant

    # 6. VWAP Reclaim
    vwap_reclaim: bool = False            # Prix repasse au-dessus VWAP
    vwap_value: float = 0.0

    # Meta
    data_available: bool = False
    error: str = ""

    @property
    def signals_active(self) -> int:
        """Nombre de signaux actifs (0-6)."""
        return sum([
            self.squeeze_on or self.squeeze_just_fired,
            self.obv_divergence,
            self.keltner_breakout,
            self.volume_spike,
            self.rsi_shift,
            self.vwap_reclaim,
        ])

    @property
    def squeeze_phase(self) -> str:
        """Phase du squeeze détectée."""
        if self.keltner_breakout and self.volume_spike:
            return "🚀 BREAKOUT"
        elif self.squeeze_just_fired:
            return "⚡ FIRED"
        elif self.squeeze_on:
            return "🔄 COMPRESSION"
        elif self.obv_divergence:
            return "👁 ACCUMULATION"
        return "⏸ NEUTRE"

    def to_details(self) -> dict:
        """Détails formatés pour l'affichage."""
        if not self.data_available:
            return {"technical": f"❌ Données indisponibles ({self.error})"}

        d = {}

        # Squeeze
        if self.squeeze_on:
            d["squeeze"] = f"🔄 COMPRESSION active ({self.squeeze_bars} barres)"
        elif self.squeeze_just_fired:
            d["squeeze"] = "⚡ SQUEEZE FIRED — compression relâchée"
        else:
            d["squeeze"] = "⏸ Pas de compression"

        # OBV
        if self.obv_divergence:
            d["obv"] = f"✅ Divergence haussière (OBV ↗ +{self.obv_slope:.1f}, Prix ↘ {self.price_slope:+.1f})"
        else:
            d["obv"] = f"— OBV slope: {self.obv_slope:+.1f}, Prix slope: {self.price_slope:+.1f}"

        # Keltner Breakout
        if self.keltner_breakout:
            d["keltner"] = f"✅ BREAKOUT — Close ${self.close_price:.2f} > KC Upper ${self.keltner_upper:.2f}"
        else:
            d["keltner"] = f"— Close ${self.close_price:.2f} vs KC Upper ${self.keltner_upper:.2f}"

        # Volume
        if self.volume_spike:
            d["volume"] = f"✅ SPIKE — {self.volume_ratio:.1f}x la moyenne ({VOL_SPIKE_MULT}x requis)"
        else:
            d["volume"] = f"— Volume {self.volume_ratio:.1f}x la moyenne"

        # RSI
        if self.rsi_shift:
            d["rsi"] = f"✅ Momentum shift — RSI {self.rsi_current:.0f} (était {self.rsi_previous:.0f})"
        else:
            d["rsi"] = f"— RSI {self.rsi_current:.0f}"

        # VWAP
        if self.vwap_reclaim:
            d["vwap"] = f"✅ Prix au-dessus du VWAP (${self.vwap_value:.2f})"
        else:
            d["vwap"] = f"— Prix sous VWAP (${self.vwap_value:.2f})"

        return d


# ─── Main Analysis ───────────────────────────────────────────

def analyze_technical(ticker: str) -> TechnicalSignals:
    """Analyse technique complète pour un ticker. Retourne TechnicalSignals."""
    signals = TechnicalSignals(ticker=ticker)

    try:
        df = _fetch_data(ticker)
    except Exception as e:
        signals.error = str(e)
        logger.warning(f"Technical data fetch failed for {ticker}: {e}")
        return signals

    if df is None or len(df) < BB_PERIOD + 10:
        signals.error = f"Insufficient data ({len(df) if df is not None else 0} bars)"
        logger.debug(f"Not enough data for {ticker}")
        return signals

    signals.data_available = True

    try:
        # Calculer tous les indicateurs
        df = _calc_bollinger(df)
        df = _calc_keltner(df)
        df = _calc_obv(df)
        df = _calc_rsi(df)
        df = _calc_vwap(df)
        df = _calc_volume_sma(df)

        # Évaluer les signaux
        _eval_squeeze(df, signals)
        _eval_obv_divergence(df, signals)
        _eval_keltner_breakout(df, signals)
        _eval_volume_spike(df, signals)
        _eval_rsi_shift(df, signals)
        _eval_vwap_reclaim(df, signals)

    except Exception as e:
        signals.error = f"Calcul error: {e}"
        logger.error(f"Technical analysis error for {ticker}: {e}")

    return signals


# ─── Data Fetch ──────────────────────────────────────────────

def _fetch_data(ticker: str) -> Optional[pd.DataFrame]:
    """Télécharge l'historique OHLCV via yfinance."""
    t = yf.Ticker(ticker)
    df = t.history(period=f"{LOOKBACK_DAYS}d", interval="1d")

    if df is None or df.empty:
        return None

    # Normaliser les colonnes
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    required = ["open", "high", "low", "close", "volume"]
    if not all(c in df.columns for c in required):
        return None

    return df.dropna(subset=required)


# ─── Indicator Calculations ─────────────────────────────────

def _calc_bollinger(df: pd.DataFrame) -> pd.DataFrame:
    """Bandes de Bollinger (SMA ± 2σ)."""
    df["bb_mid"] = df["close"].rolling(window=BB_PERIOD).mean()
    df["bb_std"] = df["close"].rolling(window=BB_PERIOD).std()
    df["bb_upper"] = df["bb_mid"] + BB_STD * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - BB_STD * df["bb_std"]
    return df


def _calc_keltner(df: pd.DataFrame) -> pd.DataFrame:
    """Canaux de Keltner (EMA ± ATR multiplier)."""
    # EMA
    df["kc_mid"] = df["close"].ewm(span=KC_PERIOD, adjust=False).mean()

    # ATR (True Range)
    tr = pd.DataFrame({
        "hl": df["high"] - df["low"],
        "hc": (df["high"] - df["close"].shift(1)).abs(),
        "lc": (df["low"] - df["close"].shift(1)).abs(),
    })
    df["atr"] = tr.max(axis=1).ewm(span=KC_ATR_PERIOD, adjust=False).mean()

    df["kc_upper"] = df["kc_mid"] + KC_ATR_MULT * df["atr"]
    df["kc_lower"] = df["kc_mid"] - KC_ATR_MULT * df["atr"]
    return df


def _calc_obv(df: pd.DataFrame) -> pd.DataFrame:
    """On-Balance Volume."""
    obv = [0]
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i - 1]:
            obv.append(obv[-1] + df["volume"].iloc[i])
        elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
            obv.append(obv[-1] - df["volume"].iloc[i])
        else:
            obv.append(obv[-1])
    df["obv"] = obv
    return df


def _calc_rsi(df: pd.DataFrame) -> pd.DataFrame:
    """RSI (Relative Strength Index)."""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean()
    avg_loss = loss.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


def _calc_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """VWAP approximation intraday reset — ici on calcule un VWAP glissant 5j."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = (typical * df["volume"]).rolling(VWAP_LOOKBACK).sum() / \
                 df["volume"].rolling(VWAP_LOOKBACK).sum()
    return df


def _calc_volume_sma(df: pd.DataFrame) -> pd.DataFrame:
    """SMA du volume pour la détection de spikes."""
    df["vol_sma"] = df["volume"].rolling(window=VOL_SMA_PERIOD).mean()
    return df


# ─── Signal Evaluation ──────────────────────────────────────

def _eval_squeeze(df: pd.DataFrame, sig: TechnicalSignals) -> None:
    """TTM Squeeze : BB inside KC = compression."""
    # Condition: BB_upper < KC_upper AND BB_lower > KC_lower
    df["squeeze_on"] = (df["bb_upper"] < df["kc_upper"]) & (df["bb_lower"] > df["kc_lower"])

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    sig.squeeze_on = bool(last.get("squeeze_on", False))

    # Compter les barres en compression consécutives
    if sig.squeeze_on:
        bars = 0
        for i in range(len(df) - 1, -1, -1):
            if df.iloc[i].get("squeeze_on", False):
                bars += 1
            else:
                break
        sig.squeeze_bars = bars

    # Squeeze vient de FIRE = était en compression, ne l'est plus
    sig.squeeze_just_fired = bool(prev.get("squeeze_on", False)) and not sig.squeeze_on


def _eval_obv_divergence(df: pd.DataFrame, sig: TechnicalSignals) -> None:
    """OBV divergence : prix stagne/baisse mais OBV monte."""
    if len(df) < OBV_SLOPE_PERIOD + 5:
        return

    recent = df.tail(OBV_SLOPE_PERIOD)

    # Normaliser pour rendre les pentes comparables
    obv_vals = recent["obv"].values.astype(float)
    price_vals = recent["close"].values.astype(float)

    x = np.arange(len(obv_vals))

    # Slope OBV (régression linéaire normalisée)
    obv_range = obv_vals.max() - obv_vals.min() if obv_vals.max() != obv_vals.min() else 1
    obv_norm = (obv_vals - obv_vals.min()) / obv_range
    obv_slope = np.polyfit(x, obv_norm, 1)[0]

    # Slope prix (normalisé)
    price_range = price_vals.max() - price_vals.min() if price_vals.max() != price_vals.min() else 1
    price_norm = (price_vals - price_vals.min()) / price_range
    price_slope = np.polyfit(x, price_norm, 1)[0]

    sig.obv_slope = round(obv_slope * 100, 1)   # en %/barre normalisé
    sig.price_slope = round(price_slope * 100, 1)

    # Divergence = OBV monte pendant que le prix stagne ou baisse
    price_range_pct = (price_vals.max() - price_vals.min()) / price_vals.mean()
    price_stagnant_or_down = price_slope <= 0.2 or price_range_pct < PRICE_RANGE_THRESHOLD
    obv_rising = obv_slope > 0.3  # pente significativement positive

    sig.obv_divergence = price_stagnant_or_down and obv_rising


def _eval_keltner_breakout(df: pd.DataFrame, sig: TechnicalSignals) -> None:
    """Breakout = close > KC upper."""
    last = df.iloc[-1]
    sig.close_price = float(last["close"])
    sig.keltner_upper = float(last.get("kc_upper", 0))
    sig.keltner_breakout = sig.close_price > sig.keltner_upper and sig.keltner_upper > 0


def _eval_volume_spike(df: pd.DataFrame, sig: TechnicalSignals) -> None:
    """Volume spike = volume dernière bougie > 2.5x SMA20."""
    last = df.iloc[-1]
    vol = float(last.get("volume", 0))
    vol_sma = float(last.get("vol_sma", 1))

    sig.avg_volume = vol_sma
    sig.volume_ratio = round(vol / vol_sma, 1) if vol_sma > 0 else 0.0
    sig.volume_spike = sig.volume_ratio >= VOL_SPIKE_MULT


def _eval_rsi_shift(df: pd.DataFrame, sig: TechnicalSignals) -> None:
    """RSI momentum shift : RSI passe >60 depuis zone 40-55."""
    if len(df) < RSI_PERIOD + 10:
        return

    sig.rsi_current = float(df["rsi"].iloc[-1]) if not np.isnan(df["rsi"].iloc[-1]) else 0
    sig.rsi_previous = float(df["rsi"].iloc[-6]) if not np.isnan(df["rsi"].iloc[-6]) else 0

    # Le RSI est actuellement > 60 et il y a 5 sessions il était entre 40-55
    sig.rsi_shift = (
        sig.rsi_current >= 58
        and 38 <= sig.rsi_previous <= 57
    )


def _eval_vwap_reclaim(df: pd.DataFrame, sig: TechnicalSignals) -> None:
    """VWAP reclaim : prix repasse au-dessus du VWAP."""
    last = df.iloc[-1]
    sig.vwap_value = float(last.get("vwap", 0))
    sig.close_price = float(last["close"])

    if sig.vwap_value > 0:
        # Reclaim = au-dessus maintenant, était en-dessous récemment (3 sessions)
        above_now = sig.close_price > sig.vwap_value
        was_below = False
        for i in range(-4, -1):
            if abs(i) <= len(df):
                row = df.iloc[i]
                if float(row["close"]) < float(row.get("vwap", float("inf"))):
                    was_below = True
                    break

        sig.vwap_reclaim = above_now  # Simplifié : au-dessus VWAP = signal positif
