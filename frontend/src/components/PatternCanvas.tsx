import { useEffect, useRef } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

import type { Grid } from "../api/types";
import { DEFAULT_DRAW, canvasSize, cellAt, drawPattern } from "../lib/draw";

interface Props {
  grid: Grid;
  colors: Map<number, string>;
  cellPx: number;
  codeOf?: (index: number) => string;
  showCodes?: boolean;
  highlight?: [number, number][];
  protectedCells?: [number, number][];
  onCellDown(r: number, c: number): void;
  onCellEnter(r: number, c: number): void;
  onPointerUp(): void;
}

export function PatternCanvas(props: Props) {
  const { grid, colors, cellPx, codeOf, showCodes, highlight, protectedCells } = props;
  const ref = useRef<HTMLCanvasElement>(null);
  const dragging = useRef(false);
  const opts = { ...DEFAULT_DRAW, cellPx, showCodes: showCodes ?? false,
                 highlight, protectedCells, codeOf };
  const { width, height } = canvasSize(grid, opts);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;                       // jsdom 下就是 null，直接跳过
    drawPattern(ctx, grid, colors, opts);
  });

  function toCell(e: ReactPointerEvent<HTMLCanvasElement>): [number, number] | null {
    const rect = e.currentTarget.getBoundingClientRect();
    return cellAt(e.clientX - rect.left, e.clientY - rect.top, grid, opts);
  }

  return (
    <canvas
      ref={ref}
      width={width}
      height={height}
      onPointerDown={(e) => {
        const cell = toCell(e);
        if (!cell) return;
        dragging.current = true;
        e.currentTarget.setPointerCapture?.(e.pointerId);
        props.onCellDown(cell[0], cell[1]);
      }}
      onPointerMove={(e) => {
        if (!dragging.current) return;
        const cell = toCell(e);
        if (cell) props.onCellEnter(cell[0], cell[1]);
      }}
      onPointerUp={() => { dragging.current = false; props.onPointerUp(); }}
      onPointerLeave={() => { dragging.current = false; }}
    />
  );
}
