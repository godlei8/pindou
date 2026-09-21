/** 注册链接：打开就是注册页，邀请码已经填好。发给被邀请的人，不用再单独报邀请码。 */
export function inviteUrl(code: string, origin = window.location.origin): string {
  return `${origin}/register?code=${encodeURIComponent(code)}`;
}

/** 复制到剪贴板。navigator.clipboard 只在 HTTPS / localhost 下有，
 *  其他情况（比如局域网 IP 直接访问）退回到老办法。成功返回 true。 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* 用户拒绝了剪贴板权限等，走下面的老办法 */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  ta.remove();
  return ok;
}
