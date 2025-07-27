# timer_utils.py
import time

class RoundTimer:
    def __init__(self, duration_seconds):
        self.duration = duration_seconds
        self.start_time = None

    def start(self):
        """Starts or resets the timer."""
        self.start_time = time.time()

    def get_remaining_time(self):
        """Returns the remaining time in seconds, or 0 if time is up."""
        if self.start_time is None:
            return self.duration # Timer not started yet
        elapsed = time.time() - self.start_time
        remaining = self.duration - elapsed
        return max(0, remaining)

    def is_time_up(self):
        """Checks if the timer has run out."""
        return self.get_remaining_time() <= 0

    def display_time(self, round_name):
        """Prints the remaining time to the console."""
        remaining_seconds = int(self.get_remaining_time())
        minutes = remaining_seconds // 60
        seconds = remaining_seconds % 60
        print(f"[{round_name} Round Timer: {minutes:02d}:{seconds:02d} remaining]")