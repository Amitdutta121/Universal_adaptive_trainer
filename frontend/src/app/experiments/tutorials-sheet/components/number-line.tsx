/**
 * The one illustration: a number line 0..10. Numbers that `range(start, stop)` gives are filled;
 * the stop is an open circle, because the loop reaches it and quits without using it. The text
 * alternative is the live result list next to it (`describedBy`).
 *
 * Test hooks: `line-start` is the first filled dot (data-state "included"), or a dashed ring
 * (data-state "none") when the range is empty; `line-stop` is always the open circle
 * (data-state "excluded"); every filled dot is a `line-dot`.
 */

import { LINE_MAX, LINE_MIN } from "../mock-data";

const WIDTH = 440;
const PAD = 22;
const STEP = (WIDTH - PAD * 2) / (LINE_MAX - LINE_MIN);
const AXIS_Y = 40;

const x = (n: number) => PAD + (n - LINE_MIN) * STEP;

export function NumberLine({
  start,
  stop,
  values,
  describedBy,
}: {
  start: number;
  stop: number;
  values: number[];
  describedBy: string;
}) {
  const ticks = Array.from({ length: LINE_MAX - LINE_MIN + 1 }, (_, i) => LINE_MIN + i);
  const included = new Set(values);
  const empty = values.length === 0;
  // When both markers sit on the same number, push their labels apart so neither is covered.
  const together = start === stop;

  return (
    <svg
      viewBox={`0 0 ${WIDTH} 80`}
      role="img"
      aria-label={`Number line from ${LINE_MIN} to ${LINE_MAX}, start ${start}, stop ${stop}`}
      aria-describedby={describedBy}
      className="h-auto w-full"
    >
      <line
        x1={x(LINE_MIN)}
        x2={x(LINE_MAX)}
        y1={AXIS_Y}
        y2={AXIS_Y}
        className="stroke-border"
        strokeWidth={2}
      />
      {empty ? null : (
        <line
          x1={x(values[0])}
          x2={x(values[values.length - 1])}
          y1={AXIS_Y}
          y2={AXIS_Y}
          className="stroke-primary"
          strokeWidth={3}
        />
      )}

      {ticks.map((n) => (
        <g key={n}>
          {included.has(n) || n === stop ? null : (
            <circle cx={x(n)} cy={AXIS_Y} r={3} className="fill-muted-foreground" />
          )}
          <text
            x={x(n)}
            y={72}
            textAnchor="middle"
            fontSize={14}
            className="fill-muted-foreground font-mono"
          >
            {n}
          </text>
        </g>
      ))}

      {values.map((n, index) => (
        <circle
          key={n}
          cx={x(n)}
          cy={AXIS_Y}
          r={8}
          className="fill-primary"
          data-testid={index === 0 ? "line-start" : "line-dot"}
          data-state={index === 0 ? "included" : undefined}
        />
      ))}
      {empty ? (
        <circle
          cx={x(start)}
          cy={AXIS_Y}
          r={13}
          fill="none"
          className="stroke-muted-foreground"
          strokeWidth={1.5}
          strokeDasharray="3 3"
          data-testid="line-start"
          data-state="none"
        />
      ) : null}

      <circle
        cx={x(stop)}
        cy={AXIS_Y}
        r={8}
        className="fill-background stroke-foreground"
        strokeWidth={2.5}
        data-testid="line-stop"
        data-state="excluded"
      />

      <text
        x={x(start)}
        y={16}
        textAnchor={together ? "end" : "middle"}
        fontSize={14}
        className="fill-primary font-medium font-mono"
      >
        start
      </text>
      <text
        x={x(stop)}
        y={16}
        textAnchor={together ? "start" : "middle"}
        fontSize={14}
        className="fill-foreground font-medium font-mono"
      >
        stop
      </text>
    </svg>
  );
}
