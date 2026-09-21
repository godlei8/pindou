interface Props {
  /** 当前画笔颜色的色号与色值。橡皮/未选色时为 null。 */
  colorCode: string | null;
  colorHex: string | null;
  cellPx: number;
  /** 当前是否跟随窗口自动适应（没有手动缩放过）。 */
  fitted: boolean;
  canZoomIn: boolean;
  canZoomOut: boolean;
  onZoomIn(): void;
  onZoomOut(): void;
  onFit(): void;
}

export function CanvasBar(props: Props) {
  const { colorCode, colorHex, cellPx, fitted } = props;

  return (
    <div className="canvas-bar">
      <span className="current-color">
        当前颜色
        {colorHex
          ? <>
              <i style={{ background: colorHex }} aria-hidden="true" />
              <b>{colorCode}</b>
            </>
          : <b className="none">未选</b>}
      </span>

      <span className="zoom">
        <button type="button" onClick={props.onZoomOut}
                disabled={!props.canZoomOut} aria-label="缩小">−</button>
        <button type="button" onClick={props.onFit} aria-pressed={fitted}>适应</button>
        <button type="button" onClick={props.onZoomIn}
                disabled={!props.canZoomIn} aria-label="放大">+</button>
        <small>{cellPx}px/格{cellPx >= 18 ? "・显示色号" : ""}</small>
      </span>
    </div>
  );
}
