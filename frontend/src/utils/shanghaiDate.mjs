const formatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

export function shanghaiDateOffset(offsetDays = 0, now = new Date()) {
  const shifted = new Date(now.getTime() + Number(offsetDays) * 24 * 60 * 60 * 1000);
  return formatter.format(shifted);
}
