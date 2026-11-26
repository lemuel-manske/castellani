function isAborted(signal: AbortSignal): boolean {
  return signal.aborted;
}

/** Waits for a bounded delay, returning early when shutdown is requested. */
function delay(signal: AbortSignal, milliseconds: number): Promise<void> {
  if (isAborted(signal)) {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timeout);
      signal.removeEventListener("abort", finish);
      resolve();
    };

    const timeout = setTimeout(finish, milliseconds);

    signal.addEventListener("abort", finish, { once: true });

    if (isAborted(signal)) {
      finish();
    }
  });
}

export { isAborted, delay };
