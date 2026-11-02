"""Local-library episode ordering and conservative prompt timing. No Kodi imports."""
import math
import re


class Countdown:
    """Elapsed-time countdown that freezes during pause and cancels on seeking."""
    def __init__(self, now, position, duration=10.0):
        self.last_time, self.last_position = now, position
        self.duration, self.elapsed, self.cancelled = duration, 0.0, False

    def update(self, now, position, paused=False):
        delta = max(0.0, now - self.last_time)
        movement = position - self.last_position
        self.last_time, self.last_position = now, position
        if movement < -0.5 or movement > max(3.0, delta * 4):
            self.cancelled = True
        if not paused and not self.cancelled:
            self.elapsed = min(self.duration, self.elapsed + delta)
        return self.elapsed / self.duration * 100

    @property
    def complete(self):
        return not self.cancelled and self.elapsed >= self.duration


def next_episode(current, episodes):
    if current.get('type') != 'episode' or not current.get('id') or current.get('season', 0) <= 0:
        return None
    position = (current['season'], current.get('episode', 0))
    candidates = [e for e in episodes if e.get('season', 0) > 0
                  and (e['season'], e.get('episode', 0)) > position
                  and e.get('file') and e.get('file') != current.get('file')
                  and e.get('episodeid') != current['id']]
    return min(candidates, key=lambda e: (e['season'], e.get('episode', 0), e['episodeid'])) if candidates else None


def credits_start(metadata, total):
    try:
        value = metadata.get('credits_start')
        if isinstance(value, bool):
            return None
        value = float(value)
        return value if math.isfinite(value) and 0 < value < total else None
    except (ValueError, TypeError, AttributeError):
        return None


def prompt_due(position, total, marker=None, chapter='', fallback=60):
    if not all(math.isfinite(n) for n in (position, total)) or total <= 0 or position < 0 or position >= total:
        return False
    if marker is not None:
        return marker <= position
    # "Opening credits" must never trigger the end-of-episode prompt.
    named_credits = re.fullmatch(r'(?:(?:end|ending|closing|final)\s+)?credits(?:\s*[-:].*)?|outro', chapter.strip(), re.I)
    if named_credits and position >= total * 0.5:
        return True
    return fallback > 0 and total - position <= min(fallback, total * 0.1)
