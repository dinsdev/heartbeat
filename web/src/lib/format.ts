/** Minutes and seconds, such as 1:05 or 30:06. */
export function clockTime(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function count(n: number): string {
  return n.toLocaleString("en");
}

/** Minutes, seconds and tenths, such as 1:05.3, for beat times. */
export function clockTenths(seconds: number): string {
  const tenths = Math.max(0, Math.round(seconds * 10));
  const whole = Math.floor(tenths / 10);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}.${tenths % 10}`;
}
