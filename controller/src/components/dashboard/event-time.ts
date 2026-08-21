export type EventTimestamp = {
  date: string;
  time: string;
};

export function formatEventTimestamp(value: string, locale: string): EventTimestamp {
  const timestamp = new Date(value);
  const clock = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(timestamp);
  const milliseconds = String(timestamp.getMilliseconds()).padStart(3, "0");
  return {
    date: new Intl.DateTimeFormat(locale, { month: "short", day: "numeric" }).format(timestamp),
    time: `${clock}.${milliseconds}`,
  };
}
