/** 默认按 5mm 的中豆算实物尺寸，和 PDF 的 1:1 打印（导出时传的 bead_mm）一致。 */
export const BEAD_MM = 5;

/** 「宽 58 × 高 44 格」——写明哪边是宽哪边是高，只写"58×44"得猜哪个是横的。 */
export function gridText(rows: number, cols: number): string {
  return `宽 ${cols} × 高 ${rows} 格`;
}

/** 「29.0 × 22.0 cm」，先宽后高，和 gridText 顺序一致。 */
export function physicalText(rows: number, cols: number, beadMm = BEAD_MM): string {
  const cm = (n: number) => (n * beadMm / 10).toFixed(1);
  return `${cm(cols)} × ${cm(rows)} cm`;
}
