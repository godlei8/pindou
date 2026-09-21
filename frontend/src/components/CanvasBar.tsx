interface Props {
  /** 当前画笔颜色的色号与色值。橡皮/未选色时为 null。 */
  colorCode: string | null;
  colorHex: string | null;
  cellPx: number;
  /** codes = 能看清色号（默认）；fit = 整张塞进窗口；manual = 手动缩放过。 */
  mode: "codes" | "fit" | "manual";
  showsCodes: boolean;
  canZoomIn: boolean;
  canZoomOut: boolean;
  onZoomIn(): void;
  onZoomOut(): void;
  onFit(): void;
  onCodes(): void;
  /** 全屏预览：画布铺满整个屏幕，手机上看细节用。 */
  fullscreen?: boolean;
  onToggleFullscreen?(): void;
}

export function CanvasBar(props: Props) {
  const { colorCode, colorHex, cellPx, mode, showsCodes } = props;

  return (
    <div className="canvas-bar">
      <span className="current-color">
        <span className="label">当前颜色</span>
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
        {/* 两个预设：看色号（拼的时候）和看全貌（检查构图）。按下态表示当前处在哪个。 */}
        <button type="button" onClick={props.onCodes} aria-pressed={mode === "codes"}>看色号</button>
        <button type="button" onClick={props.onFit} aria-pressed={mode === "fit"}>看全貌</button>
        <button type="button" onClick={props.onZoomIn}
                disabled={!props.canZoomIn} aria-label="放大">+</button>
        <small>{cellPx}px/格{showsCodes ? "・显示色号" : ""}</small>
        {props.onToggleFullscreen && (
          <button type="button" onClick={props.onToggleFullscreen}
                  aria-pressed={props.fullscreen ?? false}>
            {props.fullscreen ? "退出全屏" : "全屏"}
          </button>
        )}
      </span>
    </div>
  );
}
