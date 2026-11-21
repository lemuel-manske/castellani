/** A sleep that `wake()` cuts short, for loops that also poll periodically. */
export class Wakeable {
  private wakeUp: (() => void) | undefined;

  sleep(ms: number): Promise<void> {
    return new Promise<void>((resolve) => {
      const done = (): void => {
        clearTimeout(timer);
        this.wakeUp = undefined;
        resolve();
      };
      const timer = setTimeout(done, Math.max(0, ms));

      this.wakeUp = done;
    });
  }

  wake(): void {
    this.wakeUp?.();
  }
}
