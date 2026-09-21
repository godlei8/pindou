import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import "./styles.css";

// 部分 App 内置浏览器（老内核 WebView）不认 dvh，body 的 height:100dvh 整条作废，
// 满高外壳塌成 0，页面只剩顶上一条。用 JS 量出可视高度当兜底，CSS 里 @supports 优先用 dvh。
function syncAppHeight() {
  document.documentElement.style.setProperty("--app-h", `${window.innerHeight}px`);
}
syncAppHeight();
window.addEventListener("resize", syncAppHeight);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
