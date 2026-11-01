/** Minutes and seconds, such as 1:05 or 30:06. */
export function clockTime(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function count(n: number): string {
  return n.toLocaleString("en");
}
