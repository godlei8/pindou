import { useEffect, useRef, useState } from "react";

/** 和后端 max_upload_bytes 及图片解码能力保持一致。 */
export const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp"];
export const MAX_BYTES = 20 * 1024 * 1024;

export type IntakeSource = "pick" | "drop" | "paste" | "sample";

/** 在发请求之前就把明显不行的挡掉，报错说清楚是什么、怎么办。 */
export function checkImage(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return `不支持${file.type ? ` ${file.type} ` : "这种"}格式，换成 PNG、JPG 或 WebP 试试`;
  }
  if (file.size > MAX_BYTES) {
    return `这张图 ${(file.size / 1024 / 1024).toFixed(1)} MB，超过了 20 MB 的上限`;
  }
  return null;
}

/** 整页接图：拖到页面任何位置都算，Ctrl+V 粘贴截图也算。
 *
 *  参照 Squoosh——不必精确瞄准一个框。拼豆图大多是从小红书/微博截图来的，
 *  截完直接粘贴是最短路径。
 *
 *  返回"是否正有文件被拖在页面上"，用来显示整页的放置提示。 */
export function useImageIntake(
  onFile: (file: File, source: IntakeSource) => void,
  enabled = true,
): boolean {
  const [dragging, setDragging] = useState(false);
  // 用 ref 存回调：否则调用方每次渲染传个新函数，监听器就要拆了重装
  const cb = useRef(onFile);
  cb.current = onFile;

  useEffect(() => {
    if (!enabled) return;

    // dragleave 在进入子元素时也会触发，只看它会让提示闪烁。数进出次数才准。
    let depth = 0;
    // 只认拖进来的是文件——拖一段文字、一个链接不该弹出"松手就开始"
    const hasFiles = (e: DragEvent) =>
      !!e.dataTransfer && Array.from(e.dataTransfer.types).includes("Files");

    const onEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth += 1;
      setDragging(true);
    };
    const onOver = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();   // 不拦的话浏览器会直接打开这张图
    };
    const onLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      const f = e.dataTransfer?.files?.[0];
      if (f) cb.current(f, "drop");
    };
    const onPaste = (e: ClipboardEvent) => {
      // 正在输入框里打字时的粘贴是粘文字，别抢
      const t = e.target as HTMLElement | null;
      if (t?.closest?.("input, textarea, [contenteditable]")) return;
      const f = Array.from(e.clipboardData?.files ?? []).find((x) => x.type.startsWith("image/"));
      if (!f) return;
      e.preventDefault();
      cb.current(f, "paste");
    };

    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragover", onOver);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("drop", onDrop);
    window.addEventListener("paste", onPaste);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("paste", onPaste);
    };
  }, [enabled]);

  return dragging;
}
