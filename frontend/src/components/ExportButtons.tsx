import { api } from "../api/client";

/** 下载是对图纸的操作，和撤销/保存同类——所以放在工具条里，不单开一个面板。
 *  腾出来的那一格高度让右栏的四个面板能一屏装下。 */
export function ExportButtons({ patternId }: { patternId: string }) {
  return (
    <div className="toolbar-group" role="group" aria-label="导出">
      <a className="btn" download
         href={api.exportUrl(patternId, { format: "png", cell_px: 28 })}>下载 PNG</a>
      <a className="btn" download
         href={api.exportUrl(patternId, { format: "pdf", bead_mm: 5 })}>下载 PDF</a>
    </div>
  );
}
